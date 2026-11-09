"""Four-channel PZT control segments of the pretraining tier.

random_actions() draws the actions of a run (since 2026-11-06, user decision; the predefined
action table inputs/actions.json and handwritten controls are no longer used);
since 2026-11-08 (user decision) pattern_run() picks the runs that use pattern_actions() instead, smooth
changes of the standing-wave patterns of the four discs around a reference point (for pretraining the
channel centre, whatever the start; around the start cluster only in runs that ask for it);
pretrain_segments() checks them against the policy limits and lays them out in time.
The frozen HF/LF schedule (Segment, Schedule, schedule(): registered 2.4/2.5/2.6 MHz, 0-1500
Pa-equivalent) was removed with the frozen HF/LF path on 2026-11-06 (user decision; last in
commit 03e0701).
"""

import math

import numpy as np

# channel order of the segments (pretrain_segments)
Y_MINUS, Y_PLUS, X_MINUS, X_PLUS = 0, 1, 2, 3


def random_actions(duration_s, segment_s, seed, max_amplitude, frequency_range_Hz, on_probability):
    """
    随机动作：把整条运行切成等长的段，每段独立随机取 4 路幅值、相位和频率。
    每路先以 on_probability 的概率决定开或关，开着的幅值在 0 到上限之间均匀随机，关着的为 0；
    相位在 0–2π 均匀随机，频率在 frequency_range_Hz 内均匀随机。同一个 seed 得到同样的动作。

    duration_s: run length [s], a whole number of segments of segment_s [s]. seed: numpy
    default_rng seed. Per segment and in this order: four on/off draws (on with probability
    on_probability), four amplitudes uniform in [0, max_amplitude) Pa-equivalent (kept for open
    channels, 0 for closed ones), four phases uniform in [0, 2 pi) rad, one frequency uniform in
    frequency_range_Hz [Hz]. Every quantity is drawn for every segment, so a segment's draws do
    not depend on the outcome of the previous ones. Channel order Y-, Y+, X-, X+. Returns the
    segments in the form pretrain_segments() takes (amplitudes, phases, duration, frequency); the
    last duration is the remainder, so the durations add up to duration_s.
    """
    count = round(duration_s / segment_s)
    if count < 1 or abs(count * segment_s - duration_s) > 1e-9 * duration_s:
        raise ValueError("duration_s must be a whole number of action segments (action_segment_s)")
    rng = np.random.default_rng(seed)
    low, high = (float(v) for v in frequency_range_Hz)
    segments = []
    elapsed = 0.0
    for k in range(count):
        on = rng.random(4) < on_probability
        amplitudes = np.where(on, rng.uniform(0.0, max_amplitude, 4), 0.0)
        phases = rng.uniform(0.0, 2 * np.pi, 4)
        frequency = rng.uniform(low, high)
        duration = segment_s if k < count - 1 else duration_s - elapsed
        elapsed += duration
        segments.append(
            dict(
                amplitudes=[float(v) for v in amplitudes],
                phases=[float(v) for v in phases],
                duration=float(duration),
                frequency=float(frequency),
            )
        )
    return segments


def pattern_run(seed, share, frequency_range_Hz):
    """
    图样族扫描的运行（2026-11-08 起，用户决定）：按动作种子决定这条运行用不用 pattern_actions()，
    用的话它的频率也在这里抽。

    seed: the run's action_seed, on its own stream numpy default_rng([seed, 1]), so that
    random_actions(seed) stays what it was. In this order, for every seed: one uniform draw (a pattern run
    when it is below share) and the frequency uniform in frequency_range_Hz [Hz]. Returns (pattern,
    frequency_Hz). (The adhesion was drawn here too until the same day; since then every run draws it,
    workflows.f10ag.contact_terms.)
    """
    rng = np.random.default_rng([seed, 1])
    pattern = bool(rng.random() < share)
    frequency = float(rng.uniform(*frequency_range_Hz))
    return pattern, frequency


def pattern_actions(duration_s, segment_s, seed, max_amplitude, frequency_Hz, pressure, gradient,
                    knot_interval_s, node_offset_max_m, zero_set_weights):
    """
    图样族扫描动作：让四枚圆片的驻波零线或零点先穿过参考点 c，再随机、平滑地转动零线、移动节点、
    在线和点之间变化（每段 segment_s，一条运行一个频率）。预训练里 c 是通道中心，与泡团在哪里无关；
    只有检验实验与仿真是否一致的运行才把 c 取在起始泡团的中心（workflows.f10ag，action_kind）。

    pressure: complex pressure per Pa-equivalent of each disc at the reference point c (channel order Y-,
    Y+, X-, X+), at frequency_Hz; gradient: its gradient [1/m per Pa-equivalent], shape (4, 3).
    Near c the X discs give plane waves along x and the Y discs along y, with local wavenumbers
    kappa_x = |Re(d/dx p_X+ / (i p_X+))| and kappa_y = |Re(d/dy p_Y+ / (i p_Y+))|. A pair (a on the minus
    side, b on the plus side) with amplitudes S / (2 |p_a|), S / (2 |p_b|) and phases turn - beta - theta_a,
    turn + beta - theta_b (theta: the disc's phase at c) gives S e^{i turn} cos(kappa s + beta) along its
    axis s from c (evidence/sculpt_4pzt_20261108/, the four patterns checked against the disc field there
    and in evidence/rotate_sheet_20261108/ (deleted 2026-11-09, user decision), evidence/morph_sheet_20261108/ (part 1, the sheet changes, deleted 2026-11-09, user decision)). Every segment uses the family
        p = -[cos(a) sin(kappa_x (x - c_x - s_x)) + (kappa_x / kappa_y) sin(a) e^{i phi} sin(kappa_y (y - c_y - s_y))],
    whose pressure gradient at (c_x + s_x, c_y + s_y) has the same size for every a and phi:
      a in [-90, 90] deg: with phi = 0 the zero line runs in direction a + 90 deg through that point, so
        a covers every direction (the pairs in phase for a > 0, opposite for a < 0);
      s_x, s_y in [-node_offset_max_m, node_offset_max_m]: the pairs' nodes move, and so the line; away
        from one pair's node the zero line is bent (more the closer to that pair's antinode, a quarter
        wavelength from its node: the wavy patterns);
      phi in [0, 90] deg: 0 a zero line; above 0 (both pairs on) only the point (c_x + s_x, c_y + s_y) stays
        a zero (a vertical line in three dimensions, a dot seen from above).
    Path: knots at t = 0 and then after intervals uniform in knot_interval_s [s] until the end of the run;
    at each knot, in this order, a uniform in [-90, 90] deg, s_x and s_y uniform in
    [-node_offset_max_m, node_offset_max_m] (both 0 at t = 0: the zero set passes through c at the
    start), one choice of phi with the weights zero_set_weights (line: 0, dot: 90 deg, between: uniform in
    0-90 deg) and one uniform draw for the "between" value; every quantity is drawn at every knot, from
    numpy default_rng([seed, 2]). In between the knots the values change linearly; each segment takes the
    values at its start. One scale for the run: its largest channel is max_amplitude Pa-equivalent.
    Returns (segments, path): segments in the form pretrain_segments() takes, as random_actions() (the last
    duration is the remainder); path: the knots and the local wavenumbers.
    """
    count = round(duration_s / segment_s)
    if count < 1 or abs(count * segment_s - duration_s) > 1e-9 * duration_s:
        raise ValueError("duration_s must be a whole number of action segments (action_segment_s)")
    rng = np.random.default_rng([seed, 2])
    kappa_x = abs((gradient[X_PLUS, 0] / (1j * pressure[X_PLUS])).real)
    kappa_y = abs((gradient[Y_PLUS, 1] / (1j * pressure[Y_PLUS])).real)
    weights = [zero_set_weights[k] for k in ("line", "dot", "between")]

    def knot():
        a = rng.uniform(-90.0, 90.0)
        offsets = rng.uniform(-node_offset_max_m, node_offset_max_m, 2)
        choice = rng.choice(3, p=weights)
        between = rng.uniform(0.0, 90.0)
        return [a, offsets[0], offsets[1], (0.0, 90.0, between)[choice]]

    times, values = [0.0], [knot()]
    values[0][1:3] = [0.0, 0.0]
    while times[-1] < duration_s:
        times.append(times[-1] + rng.uniform(*knot_interval_s))
        values.append(knot())
    values = np.array(values)
    starts = segment_s * np.arange(count)
    a, offset_x, offset_y, phi = (np.radians(np.interp(starts, times, values[:, 0])),
                                  np.interp(starts, times, values[:, 1]), np.interp(starts, times, values[:, 2]),
                                  np.radians(np.interp(starts, times, values[:, 3])))

    # the two pairs of each segment: size S, beta = pi/2 - kappa s (the node at s from c), turn
    amplitudes, phases = np.zeros((count, 4)), np.zeros((count, 4))
    pairs = ((X_MINUS, X_PLUS, np.cos(a), np.pi / 2 - kappa_x * offset_x, np.zeros(count)),
             (Y_MINUS, Y_PLUS, kappa_x / kappa_y * np.abs(np.sin(a)), np.pi / 2 - kappa_y * offset_y,
              phi + np.where(np.sin(a) < 0, np.pi, 0.0)))
    for minus, plus, size, beta, turn in pairs:
        amplitudes[:, minus] = size / (2 * abs(pressure[minus]))
        amplitudes[:, plus] = size / (2 * abs(pressure[plus]))
        phases[:, minus] = turn - beta - np.angle(pressure[minus])
        phases[:, plus] = turn + beta - np.angle(pressure[plus])
    # largest channel exactly at max_amplitude (pretrain_segments refuses anything above it, no clipping)
    amplitudes = max_amplitude * (amplitudes / amplitudes.max())
    phases = np.mod(phases, 2 * np.pi)

    segments = []
    elapsed = 0.0
    for k in range(count):
        duration = segment_s if k < count - 1 else duration_s - elapsed
        elapsed += duration
        segments.append(
            dict(
                amplitudes=[float(v) for v in amplitudes[k]],
                phases=[float(v) for v in phases[k]],
                duration=float(duration),
                frequency=float(frequency_Hz),
            )
        )
    path = dict(
        knot_times_s=[float(v) for v in times],
        direction_a_deg=[float(v) for v in values[:, 0]],
        node_offset_x_m=[float(v) for v in values[:, 1]],
        node_offset_y_m=[float(v) for v in values[:, 2]],
        phi_deg=[float(v) for v in values[:, 3]],
        kappa_x_per_m=float(kappa_x),
        kappa_y_per_m=float(kappa_y),
    )
    return segments, path


def pretrain_segments(t, max_amplitude, max_segments, frequency_range_Hz):
    """Stepped four-channel schedule for the pretraining tier.

    t["segments"]: each with amplitudes, phases, duration and frequency (from random_actions());
    channel order Y-, Y+, X-, X+;
    amplitudes in Pa-equivalent, phases in rad (Re[P exp(+i omega t)], one continuous clock,
    phases do not reset at switches). Segments are contiguous from 0 and must add up to
    t["duration"]. The source cap, segment count and frequency range come from
    configs/pretrain_policy.json. Since 2026-11-05 any frequency in frequency_range_Hz
    (2-3 MHz; 2-10 MHz since 2026-11-08, while random actions still draw from 2-3 MHz) is
    admitted: the pretraining tier computes the disc field and the bubble response
    (carried APECSS) at that frequency, with no tables. Since 2026-11-06 each segment has its
    own frequency; integrate_pretrain switches at the segment start. Returns one dict per segment (start_s, duration_s, amplitude_Pa_equivalent,
    phase_rad, frequency_Hz).
    """
    actions = t["segments"]
    if not 1 <= len(actions) <= max_segments:
        raise ValueError(f"One to {max_segments} pretraining segments required")
    low, high = (float(v) for v in frequency_range_Hz)

    def checked(frequency):
        if (
            not isinstance(frequency, (int, float))
            or isinstance(frequency, bool)
            or not math.isfinite(frequency)
            or not low <= frequency <= high
        ):
            raise ValueError(f"Pretraining frequency must lie in {low / 1e6:g}-{high / 1e6:g} MHz")
        return float(frequency)

    segments = []
    start = 0.0
    for a in actions:
        frequency = checked(a["frequency"])
        amplitudes = tuple(float(v) for v in a["amplitudes"])
        phases = tuple(float(v) for v in a["phases"])
        duration = float(a["duration"])
        if len(amplitudes) != 4 or len(phases) != 4:
            raise ValueError("Channel order must be Y-, Y+, X-, X+")
        if not all(math.isfinite(v) and 0 <= v <= max_amplitude for v in amplitudes):
            raise ValueError(
                f"Pretraining source limit 0-{max_amplitude} Pa-equivalent; no clipping"
            )
        if not all(math.isfinite(v) for v in phases):
            raise ValueError("Finite phases required")
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Positive finite segment duration required")
        segments.append(
            dict(
                start_s=start,
                duration_s=duration,
                amplitude_Pa_equivalent=amplitudes,
                phase_rad=phases,
                frequency_Hz=frequency,
            )
        )
        start += duration
    if abs(start - t["duration"]) > 1e-15:
        raise ValueError("Total duration mismatch")
    return segments
