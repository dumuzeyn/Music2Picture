from dataclasses import replace
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageChops

from m2p_controls import RenderOptions, COLOR_SCHEMES, render_with_options, parse_colors
from music2picture_v1 import ClassicAnalysis, render_classic
from music2picture_v1 import core
from music2picture_v2 import analyze_audio_array, build_visual_dna, build_visual_plan
from types import SimpleNamespace


class PlaygroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rate = 8000
        time = np.arange(rate * 4) / rate
        audio = (np.sin(2*np.pi*90*time)*.4 + np.sin(2*np.pi*430*time)*.12).astype(np.float32)
        cls.classic = ClassicAnalysis(4, core.stft_features(audio))
        dna = build_visual_dna(analyze_audio_array(audio, rate))
        cls.bundle = SimpleNamespace(visual_dna=dna, visual_plan=build_visual_plan(dna))

    def test_both_engines_and_every_color_scheme_render(self):
        for engine in ('M2Pv1', 'M2Pv2'):
            for scheme in COLOR_SCHEMES:
                with self.subTest(engine=engine, scheme=scheme):
                    options = RenderOptions(engine=engine, size=192, color_scheme=scheme,
                                            colors=('#112233', '#ABCDEF'))
                    image = render_with_options(Path('unused.wav'), options, bundle=self.bundle, classic_analysis=self.classic)
                    self.assertEqual(image.size, (192, 192))
                    self.assertGreater(float(np.asarray(image).std()), 5)

    def test_options_are_validated(self):
        for values in ({'engine':'bad'}, {'size':9000}, {'seed':-1}, {'detail':float('nan')},
                       {'contrast':300}, {'saturation':-1}, {'softness':101}, {'mood':'bad'},
                       {'composition':'bad'}, {'color_scheme':'custom'},
                       {'color_scheme':'custom', 'colors':('red',)}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                RenderOptions(**values).validated()

    def test_parameters_actually_change_result(self):
        base = RenderOptions(size=192, detail=30)
        first = render_with_options('unused.wav', base, bundle=self.bundle)
        for change in ({'seed':44}, {'detail':100}, {'saturation':0}, {'contrast':150},
                       {'softness':100}, {'color_scheme':'neon'}, {'composition':'vortex_marbling'}):
            with self.subTest(change=change):
                other = render_with_options('unused.wav', replace(base, **change), bundle=self.bundle)
                self.assertIsNotNone(ImageChops.difference(first, other).getbbox())
        repeated = render_with_options('unused.wav', base, bundle=self.bundle)
        self.assertIsNone(ImageChops.difference(first, repeated).getbbox())

    def test_changing_mood_or_metadata_reuses_audio_measurements(self):
        from music2picture_v2.pipeline import Music2PicturePipeline
        measurement = analyze_audio_array(np.zeros(8000, dtype=np.float32), 8000)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'stub.wav'
            path.write_bytes(b'stub')
            pipeline = Music2PicturePipeline(cache_size=2)
            with patch('music2picture_v2.pipeline.analyze_audio_file', return_value=measurement) as analyze:
                pipeline.analyse(path, mood_override='auto')
                pipeline.analyse(path, mood_override='calm')
                pipeline.analyse(path, metadata={'title': 'different'})
                self.assertEqual(analyze.call_count, 1)
                pipeline.analyse(path, force=True)
                self.assertEqual(analyze.call_count, 2)

    def test_silent_audio_does_not_crash_either_engine(self):
        silent = np.zeros(8000, dtype=np.float32)
        classic = ClassicAnalysis(1, core.stft_features(silent))
        dna = build_visual_dna(analyze_audio_array(silent, 8000))
        bundle = SimpleNamespace(visual_dna=dna, visual_plan=build_visual_plan(dna))
        for engine in ('M2Pv1', 'M2Pv2'):
            image = render_with_options('silence.wav', RenderOptions(engine=engine,size=128),
                                         bundle=bundle, classic_analysis=classic)
            self.assertEqual(image.size, (128,128))

    def test_classic_geometry_is_preserved_during_cleanup(self):
        original = core.sample_map_bilinear
        coordinates = []
        def record(values, x, y):
            coordinates.append((x.copy(), y.copy()))
            return original(values, x, y)
        args = self.classic.features[:5]
        with patch.object(core, 'sample_map_bilinear', side_effect=record):
            for detail in (None, 0, 100):
                core.render_random_cover(*args, 192, rng=np.random.default_rng(9), detail=detail)
        for x, y in coordinates[1:]:
            np.testing.assert_array_equal(x, coordinates[0][0])
            np.testing.assert_array_equal(y, coordinates[0][1])

    def test_classic_filter_removes_speckles_without_softening_an_edge(self):
        pixels = np.zeros((32,32,3), dtype=np.uint8)
        pixels[:,16:] = 255
        pixels[8,8] = 255
        filtered = core.remove_classic_pixel_grain(pixels)
        self.assertEqual(set(np.unique(filtered)), {0,255})
        self.assertEqual(int(filtered[8,8].max()), 0)

    def test_legacy_color_modes_remain_distinct(self):
        results = [render_classic(size=192, seed=9, color_mode=mode, analysis=self.classic)
                   for mode in ('ocean','plasma','fusion','aurora')]
        self.assertEqual(len({image.tobytes() for image in results}), 4)

    def test_palette_has_no_color_count_limit(self):
        colors = tuple(f'#{index:02X}80C0' for index in range(50))
        RenderOptions(color_scheme='custom', colors=colors).validated()
        self.assertEqual(parse_colors(', '.join(colors)), colors)

    def test_gui_controls_match_engines_and_fit_window(self):
        from m2p_gui import Playground
        root = tk.Tk()
        root.withdraw()
        try:
            app = Playground(root)
            root.update_idletasks()
            self.assertEqual(app._options().engine, 'M2Pv2')
            self.assertEqual(str(app.mode_control['state']), 'disabled')
            app.engine.set('M2Pv1')
            self.assertEqual(str(app.mode_control['state']), 'readonly')
            self.assertEqual(str(app.composition_control['state']), 'disabled')
            app.engine.set('M2Pv3')
            self.assertEqual(app._options().engine, 'M2Pv3')
            self.assertEqual(str(app.mode_control['state']), 'disabled')
            self.assertEqual(str(app.composition_control['state']), 'readonly')
            self.assertEqual(app.timeline_note.winfo_manager(), 'pack')
            app.scheme.set('Свои цвета')
            app.colors.set('#112233, #ABCDEF')
            self.assertEqual(app._options().palette, ('#112233','#ABCDEF'))
            self.assertLess(root.winfo_reqheight(), 790)
            app.close()
        finally:
            try:
                root.destroy()
            except tk.TclError:
                pass


class EmbeddedArtworkTests(unittest.TestCase):
    def test_only_artwork_changes_and_lyrics_and_audio_bytes_survive(self):
        from m2p_id3 import ID3Frame, update_id3, read_id3
        from music2picture import embed_cover
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            song = root / 'test.mp3'
            audio = b'\xff\xfb' + bytes(range(256))*32
            song.write_bytes(audio)
            lyric = ID3Frame('USLT', b'\x00eng\x00original lyrics')
            title = ID3Frame('TIT2', b'\x03Original title')
            update_id3(song, [lyric,title])
            cover = root / 'cover.png'
            Image.new('RGB',(64,64),'purple').save(cover)
            embed_cover(song, cover)
            _,_,frames = read_id3(song)
            self.assertEqual(next(f.payload for f in frames if f.name=='USLT'), lyric.payload)
            self.assertEqual(next(f.payload for f in frames if f.name=='TIT2'), title.payload)
            self.assertTrue(song.read_bytes().endswith(audio))
            self.assertEqual(sum(f.name=='APIC' for f in frames), 1)


if __name__ == '__main__':
    unittest.main()
