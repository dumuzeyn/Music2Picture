from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import ImageChops

from m2p_controls import RenderOptions, COLOR_SCHEMES, render_with_options
from music2picture_v2 import analyze_audio_array, build_visual_dna, build_visual_plan
from music2picture_v3 import SongStructure, analyze_structure, analyze_structure_array, render_cover
from music2picture_v3.audio_analysis import _cached_structure
from music2picture_v3.renderer import timeline_fields, flowing_time_coordinates
from music2picture_v3.colors import apply_speed_colors


class Music2PictureV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rate = 8000
        t = np.arange(rate * 12) / rate
        gain = np.where(t < 6, .02, .65)
        cls.audio = (np.sin(2 * np.pi * 220 * t) * gain).astype(np.float32)
        cls.structure = analyze_structure_array(cls.audio, rate)
        cls.dna = build_visual_dna(analyze_audio_array(cls.audio, rate))
        cls.plan = build_visual_plan(cls.dna)
        cls.bundle = SimpleNamespace(visual_dna=cls.dna, visual_plan=cls.plan)

    def test_audio_timeline_keeps_quiet_opening_and_loud_ending(self):
        fields = timeline_fields(self.structure, self.dna, 256)
        self.assertGreater(fields.level[0, -32:].mean() - fields.level[0, :32].mean(), .45)
        self.assertGreater(fields.spectrum[:, -32:].mean(), fields.spectrum[:, :32].mean() * 2)
        self.assertGreater(fields.drive[0, -32:].mean(), fields.drive[0, :32].mean())

    def test_spectral_background_uses_original_time_and_low_frequencies_at_bottom(self):
        spectrum = np.zeros((128, 8), dtype=np.float32)
        spectrum[:32, 4:] = 1
        structure = SongStructure(spectrum, np.ones(8), np.zeros(8))
        fields = timeline_fields(structure, self.dna, 128)
        self.assertEqual(float(fields.spectrum[:, :32].max()), 0)
        self.assertEqual(float(fields.spectrum[:32, :].max()), 0)
        self.assertEqual(float(fields.spectrum[-16:, -16:].min()), 1)

    def test_background_order_changes_image_with_identical_dna_and_seed(self):
        options = RenderOptions(engine='M2Pv3', size=256, seed=42, color_scheme='sunset')
        reversed_structure = SongStructure(self.structure.spectrum[:, ::-1],
            self.structure.level_curve[::-1], self.structure.attack_curve[::-1])
        # Freeze global character so this tests chronological evidence alone.
        dna = replace(self.dna, activity_curve=(.5,) * 8)
        bundle = SimpleNamespace(visual_dna=dna, visual_plan=self.plan)
        first = render_with_options('unused.wav', options, bundle=bundle, song_structure=self.structure)
        other = render_with_options('unused.wav', options, bundle=bundle, song_structure=reversed_structure)
        self.assertIsNotNone(ImageChops.difference(first, other).getbbox())
        a, b = np.asarray(first).mean(axis=2), np.asarray(other).mean(axis=2)
        self.assertGreater(float(a[:, -32:].mean() - b[:, -32:].mean()), 10)
        self.assertGreater(float(b[:, :32].mean() - a[:, :32].mean()), 10)
        repeat = render_with_options('unused.wav', options, bundle=bundle, song_structure=self.structure)
        self.assertEqual(first.tobytes(), repeat.tobytes())

    def test_spectrum_change_stays_in_its_time_region(self):
        spectrum = np.full((128, 32), .2, dtype=np.float32)
        a = SongStructure(spectrum, np.full(32, .5), np.zeros(32))
        changed = spectrum.copy()
        changed[:, 24:] = .9
        b = replace(a, spectrum=changed)
        first = np.asarray(render_cover(self.dna, self.plan, a, size=256, seed=2)).astype(float)
        second = np.asarray(render_cover(self.dna, self.plan, b, size=256, seed=2)).astype(float)
        np.testing.assert_array_equal(first[:, :128], second[:, :128])
        self.assertGreater(np.abs(first[:, -32:] - second[:, -32:]).mean(), 5)

    def test_all_palettes_controls_and_resolutions_work(self):
        base = RenderOptions(engine='M2Pv3', size=192, seed=5)
        def render(options):
            return render_with_options('unused.wav', options, bundle=self.bundle, song_structure=self.structure)
        first = render(base)
        for scheme in COLOR_SCHEMES:
            image = render(replace(base, color_scheme=scheme, colors=('#112233', '#EEAA88')))
            self.assertEqual(image.size, (192, 192))
        for values in ({'seed':6}, {'detail':100}, {'softness':90}, {'saturation':0},
                       {'composition':'diagonal_pour'}, {'contrast':140}):
            with self.subTest(values=values):
                self.assertFalse(first.tobytes() == render(replace(base, **values)).tobytes())
        for size, preview in ((64, False), (1000, True), (2048, False)):
            image = render_cover(self.dna, self.plan, self.structure, size=size, seed=5, preview=preview)
            self.assertEqual(image.size, (size, size))

    def test_silence_empty_and_very_short_audio_are_finite(self):
        for audio in (np.zeros(8000), np.zeros(1), np.array([]), np.array([.5])):
            structure = analyze_structure_array(audio, 8000)
            for value in (structure.spectrum, structure.level_curve, structure.attack_curve):
                self.assertTrue(np.isfinite(value).all())
            image = render_cover(self.dna, self.plan, structure, size=64)
            self.assertEqual(image.mode, 'RGB')
        structure = analyze_structure_array(np.zeros(8000), 8000)
        self.assertEqual(float(structure.level_curve.max()), 0)
        self.assertEqual(float(structure.spectrum.max()), 0)

    def test_spectral_analysis_cache_is_reused_and_invalidated_on_source_change(self):
        _cached_structure.cache_clear()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'test.wav'
            path.write_bytes(b'audio')
            with patch('music2picture_v3.audio_analysis.decode_audio', return_value=self.audio) as decode:
                first = analyze_structure(path)
                self.assertIs(first, analyze_structure(path))
                path.write_bytes(b'changed audio')
                self.assertIsNot(first, analyze_structure(path))
                self.assertEqual(decode.call_count, 2)
        _cached_structure.cache_clear()

    def test_curved_time_coordinates_keep_order_and_endpoints(self):
        time = flowing_time_coordinates(128, 256, phase=.7)
        self.assertTrue(np.all(np.diff(time, axis=1) > 0))
        np.testing.assert_array_equal(time[:, 0], 0)
        np.testing.assert_array_equal(time[:, -1], 1)
        straight = np.linspace(0, 1, 256)[None, :]
        self.assertLess(float(np.max(np.abs(time - straight))), .04)
        self.assertGreater(float(np.ptp(time[:, 128])), .03)

    def test_speed_colors_follow_rhythm_independently_of_gain(self):
        rate = 22050
        time = np.arange(rate * 24) / rate
        profiles = []
        for bpm, gain in ((65, .35), (175, .35), (175, .10)):
            audio = np.sin(2 * np.pi * 120 * time) * np.exp(-(time % (60 / bpm)) * 30) * gain
            profiles.append(analyze_structure_array(audio, rate).speed_curve)
        self.assertGreater(float(np.median(profiles[1]) - np.median(profiles[0])), .25)
        self.assertAlmostEqual(float(np.median(profiles[1])), float(np.median(profiles[2])), delta=.08)
        from PIL import Image
        gradient = np.tile(np.linspace(0, 255, 192, dtype=np.uint8)[:, None], (1, 192))
        base = Image.fromarray(gradient).convert('RGB')
        slow = np.asarray(apply_speed_colors(base, replace(self.structure, speed_curve=(0.,)))).mean(axis=(0, 1))
        fast = np.asarray(apply_speed_colors(base, replace(self.structure, speed_curve=(1.,)))).mean(axis=(0, 1))
        self.assertGreater(slow[2], slow[0])
        self.assertGreater(fast[0], fast[2])


if __name__ == '__main__':
    unittest.main()
