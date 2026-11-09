// Pair distances and the delayed secondary force F2 of the pretraining tier, compiled
// (since 2026-11-07, user decision; evidence/pair_forces_compiled_20261107/). Called through
// ctypes by microbubble.forces.CompiledPairForces; built once per source by
// microbubble.forces.cached_pair_forces_library (g++ -O3, no FMA, see PAIR_FORCES_LIBRARY_FLAGS).
//
// pair_distances: the distance matrix of one force evaluation, shared by the collective solve,
// F2 and adhesion (each used to compute it again).
// delayed_pair_forces: F2 with the propagation delay, the same terms as the NumPy version it
// replaces (forces._pair_forces_delayed until 2026-11-07). The summation order, the powers of the
// delay factor and t^1.5 as t sqrt(t) differ, so results differ from it in the last digits
// (rounding, at most 9e-16 of the largest force in the comparison of the evidence).

#include <cmath>
#include <complex>

namespace {

using Complex = std::complex<double>;
constexpr int HARMONICS = 8;  // harmonics 1..8, as the bubble response

}  // namespace

// D (n x n, row-major): D[i n + j] = |x_i - x_j| in m, 0 on the diagonal; x: n x 3, row-major.
// The same operations as np.linalg.norm(x[:, None] - x[None], axis=-1), in the same order and
// without fused multiply-add, so bit for bit the same.
// Returns 0, or 1 if two bubbles coincide.
extern "C" int pair_distances(int n, const double* x, double* D) {
    int coincident = 0;
    for (int i = 0; i < n; ++i) {
        D[i * n + i] = 0.0;
        for (int j = i + 1; j < n; ++j) {
            const double dx = x[3 * i] - x[3 * j];
            const double dy = x[3 * i + 1] - x[3 * j + 1];
            const double dz = x[3 * i + 2] - x[3 * j + 2];
            const double d = std::sqrt(dx * dx + dy * dy + dz * dz);
            D[i * n + j] = D[j * n + i] = d;
            if (!(d > 0.0)) coincident = 1;
        }
    }
    return coincident;
}

// F2 with the propagation delay, on every bubble (f: n x 3, N, overwritten).
//   x: positions (n x 3, m); D: pair_distances(x); H: volume harmonics 1..8 (n x 8, complex, m^3);
//   P: pressure at each bubble (n, complex, Pa); u: the collective fundamental (n, complex), or
//   null for the pairwise model (isolated oscillations, with the two-bubble feedback when
//   feedback = 1); chi_zero: response per Pa where P = 0 (n, complex, one per bubble);
//   k: wavenumber (rad/m); rho_w2 = rho (2 pi f)^2; radii: the radius of every bubble (n, m;
//   since 2026-11-07 bubbles may differ in size); the remaining arguments are the Physics values
//   of the same names.
// For a pair i < j at distance d, harmonic n, kd = n k d and the delay factor of the field
// gradient g = exp(i kd) (1 - i kd), the force on i is
//   rho_w2 / (8 pi) * sum_n n^2 Re[V_i conj(V_j) g] * (x_j - x_i) / (d^2 + core^2)^1.5
// and the force on j the same with conj(V_i conj(V_j)) and the opposite direction (not equal and
// opposite: the radiation carries momentum). V is H, with u in place of the fundamental when u is
// given. core: the soft core of the near field (soft_core_over_sum S (1 - q)^2,
// q = min(d / (transition_over_sum S), 1), S = R_i + R_j the sum of the two radii).
// Returns 0, or 2 if a two-bubble feedback determinant is below 1e-6 ("Singular pair closure").
extern "C" int delayed_pair_forces(int n, const double* x, const double* D, const double* H_ri,
                                   const double* P_ri, const double* u_ri, const double* chi_zero_ri,
                                   double k, double rho_w2, const double* radii,
                                   double transition_over_sum, double soft_core_over_sum,
                                   int feedback, double feedback_end_over_sum, double* f) {
    // NumPy's complex128 arrays: real and imaginary part next to each other, as std::complex
    const Complex* H = reinterpret_cast<const Complex*>(H_ri);
    const Complex* P = reinterpret_cast<const Complex*>(P_ri);
    const Complex* u = reinterpret_cast<const Complex*>(u_ri);
    const Complex* chi_zero = reinterpret_cast<const Complex*>(chi_zero_ri);
    for (int m = 0; m < 3 * n; ++m) f[m] = 0.0;

    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            const double d = D[i * n + j];
            const double radius_sum = radii[i] + radii[j];

            // delay factors g_n = exp(i n k d) (1 - i n k d); exp(i n k d) as the n-th power
            // of exp(i k d) (one cosine and sine per pair instead of eight)
            const Complex step = std::polar(1.0, k * d);
            Complex g[HARMONICS];
            Complex phase = step;
            for (int h = 0; h < HARMONICS; ++h) {
                const double kd = (h + 1) * k * d;
                g[h] = phase * Complex(1.0, -kd);
                phase *= step;
            }

            // products of the two oscillations, weighted n^2, through the delay factors
            double corr_i = 0.0, corr_j = 0.0;
            for (int h = 0; h < HARMONICS; ++h) {
                const Complex vi = (h == 0 && u) ? u[i] : H[HARMONICS * i + h];
                const Complex vj = (h == 0 && u) ? u[j] : H[HARMONICS * j + h];
                const double pr = vi.real() * vj.real() + vi.imag() * vj.imag();  // vi conj(vj)
                const double pi = vi.imag() * vj.real() - vi.real() * vj.imag();
                const double weight = (h + 1) * (h + 1);
                const double rr = pr * g[h].real(), ii = pi * g[h].imag();
                corr_i += weight * (rr - ii);  // Re[vi conj(vj) g]
                corr_j += weight * (rr + ii);  // Re[conj(vi conj(vj)) g]
            }

            // pairwise model: the two-bubble feedback inside feedback_end_over_sum (fundamental)
            if (!u && feedback) {
                const double s = std::fmin(std::fmax((d / radius_sum - 1) / (feedback_end_over_sum - 1), 0.0), 1.0);
                const double w = 1 - s * s * (3 - 2 * s);
                if (w > 0) {
                    const Complex vi = H[HARMONICS * i], vj = H[HARMONICS * j];
                    const Complex ci = std::abs(P[i]) > 0 ? vi / P[i] : chi_zero[i];
                    const Complex cj = std::abs(P[j]) > 0 ? vj / P[j] : chi_zero[j];
                    const Complex coupling = rho_w2 / (4 * M_PI * d) * std::polar(1.0, -k * d);
                    const Complex a = coupling * ci, b = coupling * cj;
                    const Complex determinant = 1.0 - a * b;
                    if (std::abs(determinant) < 1e-6) return 2;
                    const Complex ui = (vi - a * vj) / determinant, uj = (vj - b * vi) / determinant;
                    const Complex change = ui * std::conj(uj) - vi * std::conj(vj);
                    corr_i += w * std::real(change * g[0]);
                    corr_j += w * std::real(std::conj(change) * g[0]);
                }
            }

            // soft core and the line of centres
            const double q = std::fmin(d / (transition_over_sum * radius_sum), 1.0);
            const double core = soft_core_over_sum * radius_sum * (1 - q) * (1 - q);
            const double t = d * d + core * core;
            const double scale = rho_w2 / (8 * M_PI) / (t * std::sqrt(t));  // t^1.5
            for (int c = 0; c < 3; ++c) {
                const double along = (x[3 * j + c] - x[3 * i + c]) * scale;
                f[3 * i + c] += corr_i * along;
                f[3 * j + c] -= corr_j * along;
            }
        }
    }
    return 0;
}
