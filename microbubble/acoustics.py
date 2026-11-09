"""Finite circular water sources: pressure and gradient of the four PZT discs (SI).

FNM single integral: Kelly & McGough (2006), Eq. 9, PMC2117898.
The source amplitude is rho*c*v_n (Pa-equivalent), not measured face pressure.
Re[P exp(+i omega t)]; no PDMS reflection, elastic waves or mutual source scattering.
The field is evaluated directly at the bubbles (WaterDiscs; gpu.GPUWaterDiscs on the GPU).
The stored cubic field cache and its interpolation were removed with the frozen HF/LF path on
2026-11-06 (user decision); the cache files stay in inputs/fields/ as data.
"""

from functools import lru_cache
import numpy as np
from numpy.polynomial.legendre import leggauss


@lru_cache(maxsize=8)
def _gauss_legendre(order):
    return leggauss(order)


def gauss_legendre(order):
    """leggauss(order), computed once per order; returns copies (identical numbers)."""
    if isinstance(order, bool) or int(order) != order or order < 1:
        raise ValueError("Quadrature order must be a positive integer")
    nodes, weights = _gauss_legendre(int(order))
    return nodes.copy(), weights.copy()


class WaterDiscs:
    def __init__(self, elements, frequency_Hz=2.5e6, sound_speed_m_s=1500.0):
        self.elements = elements
        self.frequency = float(frequency_Hz)
        self.k = 2 * np.pi * self.frequency / sound_speed_m_s

    def quadrature_order(self, frequency_Hz):
        """Registered FNM order of the discs at this frequency (DIRECT_QUADRATURE_ORDERS)."""
        return direct_quadrature_order(frequency_Hz)

    def evaluate(self, points, order=48):
        """Pressure and analytic derivative of the SAME converged integral."""
        x = np.atleast_2d(points)
        nodes, weights = gauss_legendre(order)
        cs = np.cos((nodes + 1) * np.pi / 2)
        weights = weights / 2
        pressures, gradients = [], []
        for e in self.elements:
            n = np.asarray(e["normal_local"], float)
            delta = x - e["center_local_m"]
            z = delta @ n
            lateral = delta - z[:, None] * n
            r = np.linalg.norm(lateral, axis=1)
            a = e["active_diameter_m"] / 2
            if np.any(z <= 0) or not np.isfinite(x).all():
                raise ValueError("Only finite points in front of each piston are admitted")
            rr, zz = r[:, None], z[:, None]
            D = rr**2 + a * a - 2 * a * rr * cs
            N = a * (a - rr * cs)
            W = N / D
            d = np.sqrt(zz**2 + D)
            E = np.exp(-1j * self.k * d)
            E0 = np.exp(-1j * self.k * zz)
            Wr = (-a * cs * D - N * (2 * rr - 2 * a * cs)) / D**2
            p = ((W * (E0 - E)) * weights).sum(1)
            pr = ((Wr * (E0 - E) + W * 1j * self.k * E * (rr - a * cs) / d) * weights).sum(1)
            pz = ((W * (-1j * self.k * E0 + 1j * self.k * E * zz / d)) * weights).sum(1)
            direction = np.divide(
                lateral, r[:, None], out=np.zeros_like(lateral), where=r[:, None] > 0
            )
            pressures.append(p)
            gradients.append(pz[:, None] * n + pr[:, None] * direction)
        return np.asarray(pressures), np.asarray(gradients)

    def rayleigh_reference(self, points, radial_order=64, angular_order=192):
        """Independent two-dimensional area quadrature including its derivative."""
        x = np.atleast_2d(points)
        t, w = leggauss(radial_order)
        angle = np.arange(angular_order) * 2 * np.pi / angular_order
        pp, gg = [], []
        for e in self.elements:
            n = np.asarray(e["normal_local"], float)
            u = np.cross(n, [0, 0, 1])
            u /= np.linalg.norm(u)
            v = np.cross(n, u)
            a = e["active_diameter_m"] / 2
            r = (t + 1) * a / 2
            src = np.asarray(e["center_local_m"]) + (
                r[:, None, None]
                * (np.cos(angle)[None, :, None] * u + np.sin(angle)[None, :, None] * v)
            ).reshape(-1, 3)
            weights = np.repeat(w * a / 2 * r * 2 * np.pi / angular_order, angular_order)
            dvec = x[:, None, :] - src
            d = np.linalg.norm(dvec, axis=-1)
            wave = np.exp(-1j * self.k * d)
            pp.append(1j * self.k / (2 * np.pi) * np.sum(wave / d * weights, axis=1))
            gg.append(
                1j
                * self.k
                / (2 * np.pi)
                * np.sum((wave * (-1j * self.k * d - 1) / d**3 * weights)[..., None] * dvec, axis=1)
            )
        return np.asarray(pp), np.asarray(gg)


class WaterSquares:
    """Finite square water sources (the PZT plates of the Y-channel chip, 2026-11-09): pressure
    and gradient (SI), same amplitude (rho*c*v_n, Pa-equivalent), time convention and interface as
    WaterDiscs (elements, frequency, k, evaluate(points, order)).

    FNM for a planar polygonal piston (McGough 2004, rectangular pistons, JASA 115:1934): the
    Rayleigh integral ik/(2 pi) * integral of exp(-ikR)/R dS, written in polar coordinates about
    the projection q of the field point onto the face, integrates exactly along each ray; what
    remains is one integral along each edge,
        p = 1/(2 pi) * sum over edges of integral_0^L (exp(-ikz) - exp(-ikR(u))) * l / s(u)^2 du,
    with z the height above the face, s(u) the in-plane distance from q to the point u along the
    edge, R = sqrt(z^2 + s^2), and l the signed distance from q to the edge line (positive on the
    inner side; edges counter-clockwise). l / s^2 du is the angle the edge element subtends at q,
    so the sum is right with q inside or outside the face, and (exp(-ikz) - exp(-ikR)) / s^2 stays
    finite as s -> 0. The gradient differentiates the same integrand (Gauss-Legendre on each edge).

    Element keys: center_local_m, normal_local (into the water), side_m, edge_axis_local (one
    in-plane edge direction).
    """

    def __init__(self, elements, frequency_Hz=2.5e6, sound_speed_m_s=1500.0):
        self.elements = elements
        self.frequency = float(frequency_Hz)
        self.k = 2 * np.pi * self.frequency / sound_speed_m_s

    def quadrature_order(self, frequency_Hz):
        """Registered FNM order per edge of the plates at this frequency (SQUARE_QUADRATURE_ORDERS)."""
        return square_quadrature_order(frequency_Hz)

    def evaluate(self, points, order=48):
        """Pressure (sources, N) and analytic gradient (sources, N, 3) of the SAME integral."""
        x = np.atleast_2d(points)
        nodes, weights = gauss_legendre(order)
        t, w = (nodes + 1) / 2, weights / 2  # on [0, 1]
        k = self.k
        pressures, gradients = [], []
        for e in self.elements:
            n, e1, e2, corners = square_frame(e)
            delta = x - e["center_local_m"]
            z = delta @ n
            if np.any(z <= 0) or not np.isfinite(x).all():
                raise ValueError("Only finite points in front of each piston are admitted")
            q = np.stack([delta @ e1, delta @ e2], axis=-1)  # projection, in-plane coordinates
            zz = z[:, None]
            E0 = np.exp(-1j * k * zz)
            p = np.zeros(len(x), complex)
            pz = np.zeros(len(x), complex)
            pq = np.zeros((len(x), 2), complex)
            for a, b in zip(corners, np.roll(corners, -1, axis=0)):
                length = np.linalg.norm(b - a)
                tangent = (b - a) / length
                outward = np.array([tangent[1], -tangent[0]])
                l = ((a - q) @ outward)[:, None]  # signed distance of q from the edge line
                d = a + (length * t)[:, None] * tangent - q[:, None, :]  # q -> edge nodes (N, M, 2)
                s2 = (d**2).sum(-1)
                R = np.sqrt(zz**2 + s2)
                E = np.exp(-1j * k * R)
                diff = E0 - E
                ww = w * length
                p += (diff * l / s2 * ww).sum(1)
                pz += ((-1j * k * E0 + 1j * k * E * zz / R) * l / s2 * ww).sum(1)
                inner = (
                    -1j * k * E * l / (R * s2) + 2 * diff * l / s2**2
                )[..., None] * d - (diff / s2)[..., None] * outward
                pq += (inner * ww[None, :, None]).sum(1)
            pressures.append(p / (2 * np.pi))
            gradients.append(
                (pz[:, None] * n + pq[:, :1] * e1 + pq[:, 1:] * e2) / (2 * np.pi)
            )
        return np.asarray(pressures), np.asarray(gradients)

    def rayleigh_reference(self, points, order=256):
        """Independent area quadrature of the Rayleigh integral over each square (order x order
        Gauss-Legendre points) and its derivative; for checks, not for runs."""
        x = np.atleast_2d(points)
        t, w = leggauss(order)
        pp, gg = [], []
        for e in self.elements:
            _, e1, e2, _ = square_frame(e)
            half = e["side_m"] / 2
            u, v = np.meshgrid(t * half, t * half, indexing="ij")
            src = np.asarray(e["center_local_m"]) + u.reshape(-1, 1) * e1 + v.reshape(-1, 1) * e2
            weights = np.outer(w, w).ravel() * half * half
            dvec = x[:, None, :] - src
            d = np.linalg.norm(dvec, axis=-1)
            wave = np.exp(-1j * self.k * d)
            pp.append(1j * self.k / (2 * np.pi) * np.sum(wave / d * weights, axis=1))
            gg.append(
                1j
                * self.k
                / (2 * np.pi)
                * np.sum((wave * (-1j * self.k * d - 1) / d**3 * weights)[..., None] * dvec, axis=1)
            )
        return np.asarray(pp), np.asarray(gg)


def square_frame(element):
    """Unit normal (into the water), in-plane axes e1 (edge_axis_local), e2 = normal x e1, and the
    four corners in (e1, e2) coordinates, counter-clockwise."""
    n = np.asarray(element["normal_local"], float)
    e1 = np.asarray(element["edge_axis_local"], float)
    e2 = np.cross(n, e1)
    h = element["side_m"] / 2
    corners = np.array([[-h, -h], [h, -h], [h, h], [-h, h]])
    return n, e1, e2, corners


# FNM quadrature order for direct evaluation at arbitrary points in the lumen (no cache).
# Order 48 is exact only near the centre: against order 800 over the whole lumen
# (|x| < 16 mm, r < 0.75 mm) it errs by 6e-10 at 2.5 MHz, 1.5e-2 at 5 MHz and 1e-1 at
# 10 MHz, while 96 points (up to 5 MHz) and 192 points (up to 10 MHz) stay below 1e-13.
# See evidence/pretrain_direct_field_20261103/DIRECT_FIELD_CHECK.json.
DIRECT_QUADRATURE_ORDERS = ((5e6, 96), (10e6, 192))


def direct_quadrature_order(frequency_Hz):
    """Registered FNM order for direct evaluation anywhere in the lumen at this frequency.

    Raises above 10 MHz (the AFG limit): no order has been checked there.
    """
    for limit_Hz, order in DIRECT_QUADRATURE_ORDERS:
        if frequency_Hz <= limit_Hz:
            return order
    raise ValueError("No checked direct-field quadrature order above 10 MHz")


# FNM order per edge of the square plates of the Y-channel chip (2026-11-09). Against order 768 at 3000
# points filling the whole Y channel: 48 points stay at 3.4e-13 (relative, pressure and gradient) up to
# 7.5 MHz but err 3e-7 at 10 MHz, 64 points stay at 5.3e-13 up to 10 MHz; 80 is taken up to 10 MHz for a
# margin. See evidence/y_channel_chip_20261109/ (ORDER_SCAN.json).
SQUARE_QUADRATURE_ORDERS = ((5e6, 48), (10e6, 80))


def square_quadrature_order(frequency_Hz):
    """Registered FNM order per edge for the square plates; raises above 10 MHz (not checked there)."""
    for limit_Hz, order in SQUARE_QUADRATURE_ORDERS:
        if frequency_Hz <= limit_Hz:
            return order
    raise ValueError("No checked square-plate quadrature order above 10 MHz")
