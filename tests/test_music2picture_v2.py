import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import ImageChops

import music2picture
import music2picture_v2
from music2picture_v2 import DescriptionStore, analyze_audio_array, build_visual_dna, build_visual_plan, generate_descriptions, render_cover


class StubValue:
    def __init__(self, **values):
        self.__dict__.update(values)

    def to_dict(self):
        return dict(self.__dict__)


class StubPipeline:
    def __init__(self, broken=()):
        self.broken = set(broken)
        self.calls = []

    def analyse(self, path, progress=None, **_kwargs):
        path = Path(path)
        self.calls.append(path.name)
        if path.name in self.broken:
            raise RuntimeError("damaged audio")
        return SimpleNamespace(
            analysis=StubValue(fingerprint=f"fp-{path.stem}"),
            visual_dna=StubValue(track=path.stem),
            visual_plan=StubValue(track=path.stem),
            song_description=f"description-{path.stem}",
            visual_brief=f"brief-{path.stem}",
            language="en",
        )


class Music2PictureV2Tests(unittest.TestCase):
    def test_renderer_has_one_public_mode_free_signature(self):
        self.assertEqual(tuple(inspect.signature(render_cover).parameters),
                         ('visual_dna', 'visual_plan', 'size', 'seed', 'preview', 'detail', 'palette', 'palette_stops', 'composition'))
        self.assertFalse(hasattr(music2picture_v2, "MODES"))
        self.assertFalse(hasattr(music2picture_v2, "select_mode"))

    def test_absolute_loudness_and_relative_dynamics_are_separate(self):
        rate = 8000
        time = np.arange(rate * 2) / rate
        quiet = analyze_audio_array((np.sin(2 * np.pi * 220 * time) * .03).astype(np.float32), rate)
        loud = analyze_audio_array((np.sin(2 * np.pi * 220 * time) * .75).astype(np.float32), rate)
        self.assertGreater(loud.rms_dbfs - quiet.rms_dbfs, 20)
        self.assertAlmostEqual(loud.relative_dynamic_range, quiet.relative_dynamic_range, delta=.08)

    def test_rendering_is_repeatable_but_tracks_change_the_image(self):
        rate = 8000
        time = np.arange(rate * 2) / rate
        first_dna = build_visual_dna(analyze_audio_array((np.sin(2 * np.pi * 70 * time) * .6).astype(np.float32), rate))
        second_dna = build_visual_dna(analyze_audio_array(np.random.default_rng(4).normal(0, .2, time.size).astype(np.float32), rate))
        first = render_cover(first_dna, build_visual_plan(first_dna), 192, 9)
        repeated = render_cover(first_dna, build_visual_plan(first_dna), 192, 9)
        second = render_cover(second_dna, build_visual_plan(second_dna), 192, 9)
        self.assertIsNone(ImageChops.difference(first, repeated).getbbox())
        self.assertIsNotNone(ImageChops.difference(first, second).getbbox())

    def test_batch_is_per_track_cached_and_error_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("one.wav", "broken.wav", "two.wav"):
                (root / name).write_bytes(name.encode())
            store = DescriptionStore(root / "cache.json")
            first = generate_descriptions(root, pipeline=StubPipeline({"broken.wav"}), store=store)
            self.assertEqual(sum(item.status == "generated" for item in first), 2)
            self.assertEqual(sum(item.status == "error" for item in first), 1)
            self.assertEqual(len({item.song_description for item in first if item.status == "generated"}), 2)
            pipeline = StubPipeline({"broken.wav"})
            second = generate_descriptions(root, pipeline=pipeline, store=DescriptionStore(root / "cache.json"))
            self.assertEqual(sum(item.status == "cached" for item in second), 2)
            self.assertEqual(pipeline.calls, ["broken.wav"])


if __name__ == "__main__":
    unittest.main()
