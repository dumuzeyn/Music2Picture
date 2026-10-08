"""Current classic rendering with archived geometry and restrained pixel grain."""
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageEnhance

from . import core

GENERATOR_VERSION = 'classic-crisp-v2'
ORIGIN_COMMIT = '342013aaa8bdb4cb86c8c14fec0acb038e50b5ca'
WORK_LIMIT = 1000


@dataclass(frozen=True)
class ClassicAnalysis:
    duration: float
    features: tuple


def analyze_track(audio_path):
    audio = core.read_audio(audio_path)
    return ClassicAnalysis(len(audio) / 22050, core.stft_features(audio))


def automatic_detail(duration, energy_curve):
    length = float(np.clip((duration - 20) / 220, 0, 1))
    curve = np.asarray(energy_curve, dtype=np.float32)
    diversity = float(np.clip((np.percentile(curve, 90) - np.percentile(curve, 10)) / .45, 0, 1)) if curve.size else 0
    return 20 + length * 20 + diversity * 20


def render_classic(audio_path=None, size=1000, seed=None, color_mode='plasma',
                   patterns=2, detail=None, analysis=None):
    analysis = analysis if analysis is not None else analyze_track(audio_path)
    color_mode = core.normalize_color_mode(color_mode)
    requested = max(64, int(size))
    work_size = min(requested, WORK_LIMIT)
    spectrum, rms, bass, mids, highs, centroid = analysis.features
    bpm = core.estimate_bpm(rms)
    bpm_curve = core.estimate_bpm_curve_from_bass(bass, work_size)
    energy_curve, energy, _ = core.estimate_energy_profile(
        spectrum, rms, bass, highs, centroid, bpm, bpm_curve, work_size)
    motion = energy_curve if color_mode in {'plasma', 'fusion', 'aurora'} else core.estimate_motion_curve(
        spectrum, rms, centroid, bpm_curve, work_size)
    resolved_detail = automatic_detail(analysis.duration, energy_curve) if detail is None else float(detail)
    if not np.isfinite(resolved_detail) or not 0 <= resolved_detail <= 100:
        raise ValueError('M2Pv1 detail must be between 0 and 100')
    rgb = core.render_random_cover(
        spectrum, rms, bass, mids, highs, work_size, patterns=patterns, bpm=bpm,
        bpm_curve=bpm_curve, color_mode=color_mode, motion_curve=motion,
        energy_curve=energy_curve, global_energy=energy, rng=np.random.default_rng(seed),
        detail=resolved_detail)
    image = Image.fromarray(rgb, 'RGB')
    image = ImageEnhance.Color(image).enhance(1.12 + .16 * energy)
    image = ImageEnhance.Contrast(image).enhance(1.03 + .12 * energy)
    if requested != work_size:
        image = image.resize((requested, requested), Image.Resampling.LANCZOS)
    return image
