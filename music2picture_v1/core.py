"""M2Pv1 classic core: historical geometry with edge-preserving grain cleanup.

Based on Music2Picture revision 342013a; packaged without audio-processing
or tag-writing entry points.
"""
import math
import subprocess
import sys

import numpy as np
from PIL import Image, ImageFilter

STARTUP_KWARGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
COLOR_MODES = {"ocean", "plasma", "fusion", "aurora"}
COLOR_MODE_ALIASES = {mode: mode for mode in COLOR_MODES}
COLOR_MODE_ALIASES.update(o="ocean", d="plasma", f="fusion", a="aurora")

def normalize_color_mode(color_mode):
    key = str(color_mode).strip().lower()
    if key not in COLOR_MODE_ALIASES:
        raise ValueError(f'color_mode must be one of: {", ".join(sorted(COLOR_MODES))} or aliases O/D/F/A')
    return COLOR_MODE_ALIASES[key]



def read_audio(audio_path, sample_rate=22050):
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "pipe:1",
    ]
    raw = subprocess.check_output(command, **STARTUP_KWARGS)
    data = np.frombuffer(raw, dtype=np.float32)
    if data.size == 0:
        raise RuntimeError(f"No audio data decoded from {audio_path}")
    peak = np.max(np.abs(data))
    return data / peak if peak > 0 else data


def stft_features(audio, n_fft=2048, hop=512):
    if audio.size < n_fft:
        audio = np.pad(audio, (0, n_fft - audio.size))
    frame_count = max(1, 1 + (audio.size - n_fft) // hop)
    usable = audio[: n_fft + hop * (frame_count - 1)]
    frames = np.lib.stride_tricks.sliding_window_view(usable, n_fft)[::hop]
    window = np.hanning(n_fft).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1)).T
    spectrum = np.log1p(spectrum)[:512]
    spectrum -= spectrum.min()
    if spectrum.max() > 0:
        spectrum /= spectrum.max()

    rms = np.sqrt(np.mean(frames * frames, axis=1))
    if rms.max() > 0:
        rms /= rms.max()

    bass = spectrum[:24].mean(axis=0)
    mids = spectrum[24:160].mean(axis=0)
    highs = spectrum[160:].mean(axis=0)
    centroid = (spectrum * np.arange(spectrum.shape[0])[:, None]).sum(axis=0) / (spectrum.sum(axis=0) + 1e-6)
    centroid /= max(1, spectrum.shape[0] - 1)
    return spectrum, rms, bass, mids, highs, centroid


def resample_axis(values, size):
    if values.size == size:
        return values
    source = np.linspace(0, 1, values.size)
    target = np.linspace(0, 1, size)
    return np.interp(target, source, values)


def sample_curve(values, positions):
    values = np.asarray(values, dtype=np.float32)
    positions = np.clip(np.asarray(positions, dtype=np.float32), 0, values.size - 1)
    low = np.floor(positions).astype(np.int32)
    high = np.clip(low + 1, 0, values.size - 1)
    amount = positions - low
    return (values[low] * (1.0 - amount) + values[high] * amount).astype(np.float32)


def sample_map_bilinear(values, x_positions, y_positions):
    values = np.asarray(values, dtype=np.float32)
    height, width = values.shape
    x = np.clip(np.asarray(x_positions, dtype=np.float32), 0, width - 1)
    y = np.clip(np.asarray(y_positions, dtype=np.float32), 0, height - 1)
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, width - 1)
    y1 = np.clip(y0 + 1, 0, height - 1)
    tx = x - x0
    ty = y - y0
    top = values[y0, x0] * (1.0 - tx) + values[y0, x1] * tx
    bottom = values[y1, x0] * (1.0 - tx) + values[y1, x1] * tx
    return (top * (1.0 - ty) + bottom * ty).astype(np.float32)


def normalize_feature(values):
    values = values.astype(np.float32)
    low = np.percentile(values, 5)
    high = np.percentile(values, 95)
    if high <= low:
        return np.zeros_like(values, dtype=np.float32)
    return np.clip((values - low) / (high - low), 0, 1).astype(np.float32)


def fixed_scale(values, low, high):
    values = np.asarray(values, dtype=np.float32)
    if high <= low:
        return np.zeros_like(values, dtype=np.float32)
    scaled = np.clip((values - low) / (high - low), 0, 1)
    return (scaled * scaled * (3.0 - 2.0 * scaled)).astype(np.float32)


def smooth_curve(values, passes=3, center_weight=3.0):
    curve = np.asarray(values, dtype=np.float32).copy()
    for _ in range(passes):
        curve = (curve * center_weight + np.roll(curve, 1) + np.roll(curve, -1)) / (center_weight + 2.0)
    return curve.astype(np.float32)


def classify_energy(score):
    if score < 0.25:
        return "CALM"
    if score < 0.45:
        return "SMOOTH"
    if score < 0.60:
        return "BALANCED"
    if score < 0.78:
        return "ENERGETIC"
    return "AGGRESSIVE"


def palette_category(score):
    if score < 0.30:
        return "violet"
    if score < 0.43:
        return "rose-violet"
    if score < 0.54:
        return "magenta"
    if score < 0.66:
        return "coral"
    if score < 0.80:
        return "amber-orange"
    if score < 0.91:
        return "orange-red"
    return "red-orange"


def resize_spectrum(spectrum, freq_bins, time_bins):
    freq_source = np.linspace(0, 1, spectrum.shape[0])
    freq_target = np.linspace(0, 1, freq_bins) ** 1.65
    temp = np.empty((freq_bins, spectrum.shape[1]), dtype=np.float32)
    for t in range(spectrum.shape[1]):
        temp[:, t] = np.interp(freq_target, freq_source, spectrum[:, t])

    time_source = np.linspace(0, 1, temp.shape[1])
    time_target = np.linspace(0, 1, time_bins)
    resized = np.empty((freq_bins, time_bins), dtype=np.float32)
    for f in range(freq_bins):
        resized[f] = np.interp(time_target, time_source, temp[f])
    return resized


def estimate_bpm(rms, sample_rate=22050, hop=512):
    if rms.size < 16:
        return 120.0

    envelope = np.maximum(0, np.diff(rms, prepend=rms[0]))
    envelope -= envelope.mean()
    if np.max(np.abs(envelope)) > 0:
        envelope /= np.max(np.abs(envelope))

    frame_rate = sample_rate / hop
    min_lag = max(1, int(frame_rate * 60 / 200))
    max_lag = min(len(envelope) - 1, int(frame_rate * 60 / 30))
    if max_lag <= min_lag:
        return 120.0

    scores = [float(np.dot(envelope[:-lag], envelope[lag:])) for lag in range(min_lag, max_lag + 1)]
    best_lag = min_lag + int(np.argmax(scores))
    bpm = 60 * frame_rate / best_lag
    while bpm < 30:
        bpm *= 2
    while bpm > 200:
        bpm /= 2
    return float(np.clip(bpm, 30, 200))


def estimate_bpm_curve_from_bass(bass, output_size, sample_rate=22050, hop=512, window_seconds=15):
    bass = bass.astype(np.float32)
    if bass.size < 8:
        return np.full(output_size, 120.0, dtype=np.float32)

    smooth = bass.copy()
    for _ in range(4):
        smooth = (smooth * 2 + np.roll(smooth, 1) + np.roll(smooth, -1)) / 4

    onset = np.maximum(0, np.diff(smooth, prepend=smooth[0]))
    threshold = np.percentile(onset, 78)
    peak_mask = (onset > threshold) & (onset >= np.roll(onset, 1)) & (onset > np.roll(onset, -1))

    frames_per_window = max(1, int(window_seconds * sample_rate / hop))
    global_bpm = estimate_bpm(bass, sample_rate=sample_rate, hop=hop)
    centers = []
    bpm_values = []

    for start in range(0, bass.size, frames_per_window):
        end = min(bass.size, start + frames_per_window)
        bpm = int(np.count_nonzero(peak_mask[start:end])) * (60.0 / window_seconds)
        if bpm < 30 or bpm > 200:
            bpm = global_bpm
        centers.append((start + end - 1) / 2)
        bpm_values.append(float(np.clip(bpm, 30, 200)))

    if len(centers) == 1:
        return np.full(output_size, bpm_values[0], dtype=np.float32)

    source = np.asarray(centers, dtype=np.float32) / max(1, bass.size - 1)
    target = np.linspace(0, 1, output_size, dtype=np.float32)
    curve = np.interp(target, source, np.asarray(bpm_values, dtype=np.float32))
    for _ in range(3):
        curve = (curve * 3 + np.roll(curve, 1) + np.roll(curve, -1)) / 5
    return np.clip(curve, 30, 200).astype(np.float32)


def estimate_motion_curve(spectrum, rms, centroid, bpm_curve, output_size, sample_rate=22050, hop=512, window_seconds=3):
    frame_count = rms.size
    if frame_count < 4:
        return np.full(output_size, 0.5, dtype=np.float32)

    rms_norm = np.clip(rms.astype(np.float32), 0, 1)
    rms_attack = np.maximum(0, np.diff(rms_norm, prepend=rms_norm[0]))
    spectral_change = np.sqrt(np.mean(np.diff(spectrum, axis=1, prepend=spectrum[:, :1]) ** 2, axis=0))
    attack_signal = rms_attack * 1.2 + spectral_change * 2.4
    attack_threshold = max(0.030, float(np.percentile(attack_signal, 72)))
    attack_peaks = (
        (attack_signal > attack_threshold)
        & (attack_signal >= np.roll(attack_signal, 1))
        & (attack_signal > np.roll(attack_signal, -1))
    )

    flux_norm = fixed_scale(spectral_change, 0.010, 0.095)
    centroid_norm = fixed_scale(centroid, 0.18, 0.70)
    frames_per_window = max(1, int(window_seconds * sample_rate / hop))
    expected_attacks = max(1.0, window_seconds * 7.0)
    centers = []
    motion_values = []

    for start in range(0, frame_count, frames_per_window):
        end = min(frame_count, start + frames_per_window)
        onset_density = min(1.0, float(np.count_nonzero(attack_peaks[start:end])) / expected_attacks)
        loudness = float(np.mean(fixed_scale(rms_norm[start:end], 0.12, 0.68)))
        flux = float(np.mean(flux_norm[start:end]))
        brightness = float(np.mean(centroid_norm[start:end]))
        rms_contrast = float(fixed_scale(np.std(rms_norm[start:end]), 0.025, 0.22))
        local_bpm = float(np.mean(bpm_curve[start * output_size // frame_count : max(start * output_size // frame_count + 1, end * output_size // frame_count)]))
        bpm_motion = float(fixed_scale(local_bpm, 85.0, 178.0))
        audio_motion = (
            0.25 * onset_density
            + 0.18 * loudness
            + 0.21 * flux
            + 0.11 * brightness
            + 0.15 * rms_contrast
            + 0.10 * bpm_motion
        )
        motion = float(np.clip(audio_motion, 0, 1))
        centers.append((start + end - 1) / 2)
        motion_values.append(motion)

    if len(centers) == 1:
        return np.full(output_size, motion_values[0], dtype=np.float32)

    source = np.asarray(centers, dtype=np.float32) / max(1, frame_count - 1)
    target = np.linspace(0, 1, output_size, dtype=np.float32)
    curve = np.interp(target, source, np.asarray(motion_values, dtype=np.float32))
    return np.clip(smooth_curve(curve, passes=2, center_weight=4.0), 0, 1).astype(np.float32)


def estimate_energy_profile(spectrum, rms, bass, highs, centroid, bpm, bpm_curve, output_size, sample_rate=22050, hop=512):
    frame_count = rms.size
    if frame_count < 4:
        curve = np.full(output_size, 0.5, dtype=np.float32)
        diagnostics = {
            "attack_density": 0.0,
            "spectral_flux": 0.0,
            "rms_contrast": 0.0,
            "peak_density": 0.0,
            "bass_hits": 0.0,
            "high_energy": 0.0,
            "spectral_smoothness": 1.0,
        }
        return curve, 0.5, diagnostics

    duration = max(frame_count * hop / sample_rate, 1e-6)
    rms_norm = np.clip(rms.astype(np.float32), 0, 1)
    bass_norm = np.clip(bass.astype(np.float32), 0, 1)
    highs_norm = np.clip(highs.astype(np.float32), 0, 1)
    spectral_change = np.sqrt(np.mean(np.diff(spectrum, axis=1, prepend=spectrum[:, :1]) ** 2, axis=0))
    rms_jump = np.maximum(0, np.diff(rms_norm, prepend=rms_norm[0]))
    bass_jump = np.maximum(0, np.diff(bass_norm, prepend=bass_norm[0]))
    attack_signal = rms_jump * 1.25 + spectral_change * 2.35 + bass_jump * 0.35
    attack_threshold = max(0.032, float(np.percentile(attack_signal, 74)))
    attack_peaks = (
        (attack_signal > attack_threshold)
        & (attack_signal >= np.roll(attack_signal, 1))
        & (attack_signal > np.roll(attack_signal, -1))
    )
    strong_peak_mask = (
        (rms_norm > max(0.55, float(np.percentile(rms_norm, 88))))
        & (rms_norm >= np.roll(rms_norm, 1))
        & (rms_norm > np.roll(rms_norm, -1))
    )
    bass_hit_mask = (
        (bass_jump > max(0.025, float(np.percentile(bass_jump, 82))))
        & (bass_jump >= np.roll(bass_jump, 1))
        & (bass_jump > np.roll(bass_jump, -1))
    )

    local_bpm = resample_axis(bpm_curve, frame_count)
    attack_density_curve = smooth_curve(attack_peaks.astype(np.float32), passes=5, center_weight=5.0)
    peak_density_curve = smooth_curve(strong_peak_mask.astype(np.float32), passes=6, center_weight=5.0)
    bass_hit_curve = smooth_curve(bass_hit_mask.astype(np.float32), passes=5, center_weight=5.0)
    local_energy = (
        0.16 * fixed_scale(local_bpm, 90.0, 178.0)
        + 0.19 * fixed_scale(attack_density_curve, 0.015, 0.18)
        + 0.20 * fixed_scale(spectral_change, 0.010, 0.095)
        + 0.13 * fixed_scale(rms_jump, 0.010, 0.085)
        + 0.12 * fixed_scale(peak_density_curve, 0.010, 0.120)
        + 0.08 * fixed_scale(np.abs(rms_norm - smooth_curve(rms_norm, passes=8, center_weight=3.0)), 0.015, 0.18)
        + 0.07 * fixed_scale(highs_norm, 0.18, 0.66)
        + 0.05 * fixed_scale(bass_hit_curve, 0.010, 0.120)
    )
    local_energy = np.clip(smooth_curve(local_energy, passes=2, center_weight=4.0), 0, 1)

    diagnostics = {
        "attack_density": float(np.count_nonzero(attack_peaks) / duration),
        "spectral_flux": float(np.mean(spectral_change)),
        "rms_contrast": float(np.std(rms_norm)),
        "peak_density": float(np.count_nonzero(strong_peak_mask) / duration),
        "bass_hits": float(np.count_nonzero(bass_hit_mask) / duration),
        "high_energy": float(np.mean(highs_norm)),
        "spectral_smoothness": float(1.0 - np.clip(np.mean(spectral_change) / 0.11, 0, 1)),
    }
    global_energy = (
        0.16 * float(fixed_scale(bpm, 88.0, 178.0))
        + 0.17 * float(fixed_scale(diagnostics["attack_density"], 0.7, 8.5))
        + 0.18 * float(fixed_scale(diagnostics["spectral_flux"], 0.010, 0.090))
        + 0.14 * float(fixed_scale(diagnostics["rms_contrast"], 0.035, 0.240))
        + 0.13 * float(fixed_scale(diagnostics["peak_density"], 0.10, 2.8))
        + 0.10 * float(fixed_scale(diagnostics["high_energy"], 0.18, 0.62))
        + 0.07 * float(fixed_scale(diagnostics["bass_hits"], 0.15, 4.0))
        + 0.05 * (1.0 - diagnostics["spectral_smoothness"])
    )
    global_energy = float(np.clip(global_energy, 0, 1))
    curve = resample_axis(local_energy, output_size)
    curve = np.clip(0.72 * curve + 0.28 * global_energy, 0, 1).astype(np.float32)
    return curve, global_energy, diagnostics


def peak_emphasis(values):
    values = values.astype(np.float32)
    smooth = values.copy()
    for _ in range(6):
        smooth = (smooth * 2 + np.roll(smooth, 1) + np.roll(smooth, -1)) / 4
    peaks = np.maximum(0, values - smooth)
    if peaks.max() > 0:
        peaks /= peaks.max()
    peaks = np.power(peaks, 0.55)
    for _ in range(4):
        peaks = (peaks * 3 + np.roll(peaks, 1) + np.roll(peaks, -1)) / 5
    return np.clip(peaks, 0, 1)


def bpm_to_hue(bpm):
    position = np.clip((bpm - 40.0) / 160.0, 0, 1)
    return 0.78 * position


def motion_to_hue(motion):
    motion = np.clip(motion, 0, 1)
    stops = np.asarray([0.00, 0.15, 0.30, 0.45, 0.58, 0.70, 0.82, 0.92, 1.00], dtype=np.float32)
    hues = np.asarray([0.76, 0.77, 0.79, 0.72, 0.88, 0.91, 0.96, 0.00, 0.04], dtype=np.float32)
    return np.interp(motion.reshape(-1), stops, hues).reshape(motion.shape).astype(np.float32)


def energy_to_rgb(energy):
    energy = np.clip(np.asarray(energy, dtype=np.float32), 0, 1)
    stops = np.asarray([0.00, 0.16, 0.29, 0.42, 0.54, 0.66, 0.78, 0.90, 1.00], dtype=np.float32)
    colors = np.asarray(
        [
            (22, 6, 42),
            (68, 18, 126),
            (86, 54, 168),
            (168, 54, 152),
            (222, 82, 126),
            (224, 104, 84),
            (224, 134, 48),
            (218, 62, 80),
            (246, 88, 40),
        ],
        dtype=np.float32,
    ) / 255.0
    flat = energy.reshape(-1)
    channels = [np.interp(flat, stops, colors[:, channel]) for channel in range(3)]
    return np.stack(channels, axis=-1).reshape(energy.shape + (3,)).astype(np.float32)


def local_contrast_edge_rgb(base_rgb, edge_strength, smooth_contrast=False):
    base_rgb = np.clip(np.asarray(base_rgb, dtype=np.float32), 0, 1)
    edge_strength = np.clip(np.asarray(edge_strength, dtype=np.float32), 0, 1)
    luminance = base_rgb[..., 0] * 0.2126 + base_rgb[..., 1] * 0.7152 + base_rgb[..., 2] * 0.0722
    gray = luminance[..., None]
    saturated = np.clip(gray + (base_rgb - gray) * (1.30 + edge_strength[..., None] * 0.55), 0, 1)
    darker = np.clip(saturated * (0.30 - edge_strength[..., None] * 0.08), 0, 1)
    lighter = np.clip(1.0 - (1.0 - saturated) * (0.42 - edge_strength[..., None] * 0.10), 0, 1)
    if smooth_contrast:
        # A binary light/dark switch amplifies tiny audio/color fluctuations into
        # black-white speckles. Blend the rim tone, not its spatial geometry.
        dark_mix = np.clip((luminance - .34) / .16, 0, 1)
        dark_mix = dark_mix * dark_mix * (3 - 2 * dark_mix)
        return (lighter * (1 - dark_mix[..., None]) + darker * dark_mix[..., None]).astype(np.float32)
    return np.where((luminance > 0.42)[..., None], darker, lighter).astype(np.float32)


def apply_local_pattern_edges(rgb, pattern_edge, high_map, spectrum_value, sharp_mix, edge_gain=1.0, smooth_contrast=False):
    pattern_edge = pattern_edge * edge_gain
    neighbor_rgb = (
        np.roll(rgb, 3, axis=0)
        + np.roll(rgb, -3, axis=0)
        + np.roll(rgb, 3, axis=1)
        + np.roll(rgb, -3, axis=1)
    ) * 0.25
    rim_edge = np.clip(pattern_edge * (0.38 + high_map * 0.30 + spectrum_value * 0.12), 0, 0.62)
    rim_color = local_contrast_edge_rgb(neighbor_rgb, pattern_edge, smooth_contrast)
    shadow_edge = np.clip(pattern_edge * (0.38 + sharp_mix * 0.34), 0, 0.58)
    rgb = rgb * (1.0 - shadow_edge[..., None] * (1.0 - rim_edge[..., None] * 0.35))
    return rgb * (1.0 - rim_edge[..., None]) + rim_color * rim_edge[..., None]


def hsv_to_rgb_array(h, s, v):
    h = np.mod(h, 1.0)
    i = np.floor(h * 6).astype(np.int32)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    i = np.mod(i, 6)

    rgb = np.zeros(h.shape + (3,), dtype=np.float32)
    masks = [i == n for n in range(6)]
    rgb[masks[0]] = np.stack([v, t, p], axis=-1)[masks[0]]
    rgb[masks[1]] = np.stack([q, v, p], axis=-1)[masks[1]]
    rgb[masks[2]] = np.stack([p, v, t], axis=-1)[masks[2]]
    rgb[masks[3]] = np.stack([p, q, v], axis=-1)[masks[3]]
    rgb[masks[4]] = np.stack([t, p, v], axis=-1)[masks[4]]
    rgb[masks[5]] = np.stack([v, p, q], axis=-1)[masks[5]]
    return rgb


def smooth_random_field(size, cells, rng, detail=0.0):
    small = rng.random((cells, cells), dtype=np.float32)
    image = Image.fromarray(np.uint8(small * 255), "L")
    image = image.resize((size, size), Image.Resampling.BICUBIC)
    field = np.asarray(image).astype(np.float32) / 255
    if detail > 0:
        detail_cells = max(cells * 4, cells + 8)
        small_detail = rng.random((detail_cells, detail_cells), dtype=np.float32)
        detail_image = Image.fromarray(np.uint8(small_detail * 255), "L")
        detail_image = detail_image.resize((size, size), Image.Resampling.BILINEAR)
        detail_field = np.asarray(detail_image).astype(np.float32) / 255
        field = field * (1.0 - detail) + detail_field * detail
    field -= field.min()
    if field.max() > 0:
        field /= field.max()
    return field.astype(np.float32)


def smooth_artwork_field(field, passes=2):
    """Remove single-pixel chatter before warping, without changing broad forms."""
    field = np.asarray(field, dtype=np.float32)
    for _ in range(passes):
        padded = np.pad(field, ((0, 0), (1, 1)), mode='edge')
        field = (padded[:, :-2] + padded[:, 1:-1] * 2 + padded[:, 2:]) * .25
        padded = np.pad(field, ((1, 1), (0, 0)), mode='edge')
        field = (padded[:-2] + padded[1:-1] * 2 + padded[2:]) * .25
    return field


def remove_classic_pixel_grain(rgb):
    """Reject isolated pixel outliers without averaging across contour edges."""
    return np.asarray(Image.fromarray(rgb, 'RGB').filter(ImageFilter.MedianFilter(3)))


def render_random_cover(
    spec,
    rms,
    bass,
    mids,
    highs,
    size,
    patterns=2,
    bpm=120.0,
    bpm_curve=None,
    color_mode="ocean",
    motion_curve=None,
    energy_curve=None,
    global_energy=0.5,
    rng=None,
    detail=None,
):
    # None keeps the archived reference renderer available unchanged. SonicForge
    # supplies a continuous 0..100 detail value for its cleaned classic artwork.
    clean = detail is not None
    detail_level = float(np.clip(float(detail) / 100, 0, 1)) if clean else 1.0
    if clean and not np.isfinite(detail_level):
        raise ValueError('Classic detail must be finite')
    edge_gain = .70 + detail_level * .25 if clean else 1.0
    if rng is None:
        rng = np.random.default_rng()
    song_map = resize_spectrum(spec, freq_bins=size, time_bins=size)
    song_map = np.flipud(song_map)
    if clean:
        # Filter only the audio magnitude map before warping. The historical
        # fields, angular boundaries and decorative contours remain untouched.
        song_map = smooth_artwork_field(song_map, passes=2)
    if bpm_curve is None:
        bpm_curve = np.full(size, bpm, dtype=np.float32)
    if motion_curve is None:
        motion_curve = np.full(size, 0.5, dtype=np.float32)
    if energy_curve is None:
        energy_curve = motion_curve

    volume = resample_axis(rms, size)
    bass_line = resample_axis(bass, size)
    mids_line = resample_axis(mids, size)
    highs_line = resample_axis(highs, size)
    peaks = peak_emphasis(volume)

    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    base_part = size - 1 - yy
    base_freq = xx

    calm_cells = int(round(8 + 8 * global_energy))
    sharp_cells = int(round(18 + 18 * global_energy))
    detail_amount = 0.12 + 0.20 * global_energy
    field_a = smooth_random_field(size, cells=calm_cells, rng=rng, detail=detail_amount * 0.55)
    field_b = smooth_random_field(size, cells=sharp_cells, rng=rng, detail=detail_amount)
    field_c = smooth_random_field(size, cells=max(7, calm_cells - 2), rng=rng, detail=detail_amount * 0.70)
    field_d = smooth_random_field(size, cells=max(24, sharp_cells + 8),
                                  rng=rng, detail=min(0.42, detail_amount + 0.10))
    micro_field = smooth_random_field(size, cells=max(36, sharp_cells * 2),
                                      rng=rng, detail=.36)

    initial_part = np.clip(base_part + (field_a - 0.5) * 46 + (field_d - 0.5) * 28, 0, size - 1)
    peak_rows = sample_curve(peaks, initial_part)
    energy_rows = sample_curve(energy_curve, initial_part)
    calm = 1.0 - energy_rows
    sharp_mix = np.clip(energy_rows * 0.92 + peak_rows * 0.55, 0, 1)
    smooth_part = (field_a - 0.5) * (42 + 62 * calm)
    smooth_freq = (field_c - 0.5) * (55 + 78 * calm)
    angular = (np.abs(field_d - 0.5) * 2.0 - 0.5) * np.sign(field_b - 0.5)
    sharp_part = angular * (42 + 168 * sharp_mix)
    sharp_freq = (field_b - 0.5) * (58 + 205 * sharp_mix)
    part_warp = smooth_part * (1.0 - sharp_mix) + sharp_part * sharp_mix
    freq_warp = smooth_freq * (1.0 - sharp_mix) + sharp_freq * sharp_mix
    pattern_signal = np.zeros_like(field_a, dtype=np.float32)
    pattern_edge = np.zeros_like(field_a, dtype=np.float32)
    if patterns >= 2:
        wave_soft = np.sin((xx * 0.010 + field_c * 5.5) * math.pi) * (20 + 45 * calm)
        triangle = 2.0 * np.abs(((xx * (0.010 + 0.012 * sharp_mix) + field_d * 4.0) % 1.0) - 0.5) - 0.5
        part_warp += wave_soft * (1.0 - sharp_mix) + triangle * (42 + 118 * sharp_mix)
        freq_warp += np.sin((yy * 0.012 + field_a * 7) * math.pi) * (24 + 102 * sharp_mix)
        curve_angle = (xx * (0.016 + 0.010 * global_energy) + yy * (0.006 + 0.008 * global_energy))
        curve_angle += field_a * 4.2 + field_b * 2.4 - field_c * 3.0
        stripe = np.sin(curve_angle * math.pi)
        ridge = np.power(np.clip(np.abs(stripe), 0, 1), 0.34)
        broken_ridge = ridge * np.clip(0.46 + field_d * 0.58 + np.abs(field_a - field_b) * 0.46, 0, 1)
        pattern_signal = (broken_ridge - 0.5).astype(np.float32)
        edge_core = 1.0 - np.clip(np.abs(stripe) * 4.2, 0, 1)
        edge_breakup = np.clip(0.46 + field_b * 0.76 + np.abs(field_c - field_d) * 0.62, 0, 1)
        pattern_edge = np.power(edge_core, 0.34).astype(np.float32) * edge_breakup
        part_warp += (broken_ridge - 0.5) * (20 + 74 * sharp_mix)
        freq_warp += stripe * (18 + 62 * sharp_mix)

    part_pos = np.clip(base_part + part_warp, 0, size - 1)
    freq_pos = np.clip(base_freq + freq_warp, 0, size - 1)

    spectrum_value = sample_map_bilinear(song_map, part_pos, freq_pos)
    spectrum_detail = np.clip(
        (micro_field - 0.5) * 0.050 + (field_d - 0.5) * 0.030 + pattern_signal * 0.070 + pattern_edge * 0.125,
        -0.13,
        0.16,
    )
    spectrum_value = np.clip(spectrum_value + spectrum_detail, 0, 1)
    local_bpm = sample_curve(bpm_curve, part_pos)
    local_energy = sample_curve(energy_curve, part_pos)
    peak_rows = sample_curve(peaks, part_pos)
    energy_rows = local_energy
    sharp_mix = np.clip(energy_rows * 0.92 + peak_rows * 0.55, 0, 1)

    bass_map = sample_curve(bass_line, part_pos)
    mid_map = sample_curve(mids_line, part_pos)
    high_map = sample_curve(highs_line, part_pos)
    volume_map = sample_curve(volume, part_pos)
    if color_mode == "ocean":
        bpm_texture = (field_a - 0.5) * (1.6 + 1.2 * peak_rows) + pattern_signal * 1.1
        pixel_bpm = (local_bpm + bpm_texture).astype(np.float32)
        pixel_bpm = np.clip(pixel_bpm, 30, 200)

        hue_shift = (field_a - 0.5) * 0.014 + pattern_signal * 0.010 + spectrum_value * 0.006
        red_lock = np.clip((40.0 - pixel_bpm) / 10.0, 0, 1)
        hue_shift = np.where(red_lock > 0, np.minimum(hue_shift, 0), hue_shift)
        hue = np.mod(bpm_to_hue(pixel_bpm) + hue_shift, 1.0)
        saturation = np.clip(0.52 + spectrum_value * 0.18 + high_map * 0.08 + peak_rows * 0.12, 0, 1)
        value = np.clip(0.14 + spectrum_value * 0.48 + volume_map * 0.28 + bass_map * 0.10 + peak_rows * 0.30, 0, 1)
    elif color_mode in {"plasma", "fusion", "aurora"}:
        brightness_bias = np.clip((float(np.mean(highs_line)) - float(np.mean(bass_line))) * 0.18, -0.08, 0.08)
        bass_bias = np.clip((float(np.mean(bass_line)) - 0.38) * 0.10, -0.04, 0.05)
        color_energy = np.clip(global_energy + brightness_bias + bass_bias, 0, 1)
        base_energy = np.clip(0.56 * color_energy + 0.44 * local_energy, 0, 1)
        energy_sigma = 0.012 + 0.026 * sharp_mix
        if clean:
            # Coherent color variation, not an independent random value per pixel.
            pixel_energy = base_energy + (field_c - .5) * energy_sigma * (.3 + detail_level * .4)
        else:
            pixel_energy = rng.normal(base_energy, energy_sigma).astype(np.float32)
        pixel_energy = np.clip(
            pixel_energy
            + (spectrum_value - 0.50) * 0.050
            + (micro_field - 0.5) * 0.025
            + pattern_signal * 0.055
            + pattern_edge * 0.085
            + peak_rows * 0.025,
            0,
            1,
        )
        rgb = energy_to_rgb(pixel_energy)
        saturation_boost = np.clip(0.82 + spectrum_value * 0.22 + sharp_mix * 0.18, 0.78, 1.22)
        value = np.clip(0.13 + spectrum_value * 0.54 + volume_map * 0.24 + bass_map * 0.10 + peak_rows * (0.18 + 0.20 * global_energy), 0, 1)
        rgb *= saturation_boost[..., None] * value[..., None] / np.maximum(rgb.max(axis=-1, keepdims=True), 0.08)
        if color_mode == "plasma":
            plasma_wave = np.sin((xx * 0.016 - yy * 0.010 + field_d * 5.0 + field_a * 1.6) * math.pi)
            plasma_lane = np.power(np.clip(plasma_wave * 0.5 + 0.5, 0, 1), 3.2)
            plasma_lane *= np.clip(0.42 + sharp_mix * 0.48 + peak_rows * 0.28, 0, 1)
            cool = np.asarray((0.08, 0.42, 1.00), dtype=np.float32)
            hot = np.asarray((1.00, 0.18, 0.54), dtype=np.float32)
            lane_color = cool * (1.0 - local_energy[..., None]) + hot * local_energy[..., None]
            rgb = rgb * (1.0 - plasma_lane[..., None] * 0.30) + lane_color * (plasma_lane[..., None] * 0.30)
            rgb = np.clip((rgb - 0.5) * 1.10 + 0.5, 0, 1)
        elif color_mode == "aurora":
            aurora_phase = yy * (0.008 + 0.004 * global_energy) - xx * 0.004 + field_a * 4.4 + field_c * 2.1
            aurora_wave = np.sin(aurora_phase * math.pi) * 0.5 + 0.5
            aurora_band = np.power(np.clip(aurora_wave, 0, 1), 2.8)
            aurora_band *= np.clip(0.34 + volume_map * 0.34 + high_map * 0.22 + (1.0 - sharp_mix) * 0.16, 0, 1)
            teal = np.asarray((0.06, 0.92, 0.72), dtype=np.float32)
            violet = np.asarray((0.54, 0.18, 1.00), dtype=np.float32)
            rose = np.asarray((1.00, 0.18, 0.72), dtype=np.float32)
            aurora_color = teal * (1.0 - local_energy[..., None]) + violet * local_energy[..., None]
            rose_mix = np.clip(high_map * 0.45 + spectrum_value * 0.24, 0, 0.55)[..., None]
            aurora_color = aurora_color * (1.0 - rose_mix) + rose * rose_mix
            rgb = rgb * (1.0 - aurora_band[..., None] * 0.34) + aurora_color * (aurora_band[..., None] * 0.34)
            rgb = np.clip(rgb * (0.94 + aurora_band[..., None] * 0.26), 0, 1)
    else:
        raise ValueError(f"Unknown color mode: {color_mode}")

    edge_pattern = (
        np.abs(np.gradient(field_a, axis=0))
        + np.abs(np.gradient(field_b, axis=1))
        + np.abs(np.gradient(micro_field, axis=0)) * 0.72
        + np.abs(np.gradient(micro_field, axis=1)) * 0.72
        + np.abs(np.gradient(pattern_signal, axis=0)) * 1.25
        + np.abs(np.gradient(pattern_signal, axis=1)) * 1.25
        + pattern_edge * 2.15
    )
    edge_pattern = np.clip(edge_pattern * (11 + 28 * sharp_mix), 0, 1)
    if clean:
        edge_pattern *= edge_gain
    if color_mode == "ocean":
        rgb = hsv_to_rgb_array(hue, saturation, value)
        rgb = apply_local_pattern_edges(rgb, pattern_edge, high_map, spectrum_value, sharp_mix, edge_gain, clean)
    elif color_mode in {"plasma", "fusion", "aurora"}:
        accent_mask = np.clip((high_map - 0.82) * 1.65 + edge_pattern * 0.045, 0, 1)
        accent_mask *= np.clip(pixel_energy - 0.58, 0, 0.42) / 0.42
        accent = np.asarray((1.00, 0.48, 0.10), dtype=np.float32)
        warm_strength = 0.040 if color_mode == "plasma" else (0.035 if color_mode == "aurora" else 0.055)
        rgb = rgb * (1.0 - accent_mask[..., None] * warm_strength) + accent * (accent_mask[..., None] * warm_strength)
        blue_mask = np.clip((field_b - 0.48) * 2.65 + (high_map - bass_map) * 1.75 + spectrum_value * 0.30 + edge_pattern * 0.15, 0, 1)
        blue_mask *= np.clip(0.92 - pixel_energy, 0, 0.92) / 0.92
        blue = np.asarray((0.06, 0.26, 1.00), dtype=np.float32)
        blue_strength = 0.38 if color_mode == "plasma" else (0.42 if color_mode == "aurora" else 0.50)
        rgb = rgb * (1.0 - blue_mask[..., None] * blue_strength) + blue * (blue_mask[..., None] * blue_strength)
        green_mask = np.clip((field_c - 0.40) * 2.65 + (mid_map + bass_map - high_map * 0.35) * 0.95 + (1.0 - sharp_mix) * 0.24, 0, 1)
        green_mask *= np.clip(0.86 - pixel_energy, 0, 0.86) / 0.86
        green = np.asarray((0.04, 0.78, 0.34), dtype=np.float32)
        green_strength = 0.28 if color_mode == "plasma" else (0.34 if color_mode == "aurora" else 0.52)
        rgb = rgb * (1.0 - green_mask[..., None] * green_strength) + green * (green_mask[..., None] * green_strength)
        rgb = apply_local_pattern_edges(rgb, pattern_edge, high_map, spectrum_value, sharp_mix, edge_gain, clean)
    rgb *= np.clip(0.90 + edge_pattern[..., None] * (0.14 + sharp_mix[..., None] * 0.78), 0.70, 1.30)
    pixels = np.clip(rgb * 255, 0, 255).astype(np.uint8)
    return remove_classic_pixel_grain(pixels) if clean else pixels
