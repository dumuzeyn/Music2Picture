"""Non-interactive smoke test for the frozen EXE; never uses personal music."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import time
import traceback
import wave

import numpy as np


def run(report_path):
    report = {'ok': False, 'checks': []}
    try:
        import tkinter as tk
        from m2p_controls import RenderOptions, COLOR_SCHEMES, render_with_options, VERSION
        from m2p_gui import Playground
        from music2picture_v1 import analyze_track
        from music2picture_v2 import DEFAULT_PIPELINE
        report['version'] = VERSION
        with tempfile.TemporaryDirectory(prefix='m2p-check-') as directory:
            source = Path(directory) / 'synthetic.wav'
            rate = 22050
            t = np.arange(rate * 4) / rate
            sound = np.sin(2*np.pi*150*t)*.3 + np.sin(2*np.pi*480*t)*.12
            with wave.open(str(source), 'wb') as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(rate)
                stream.writeframes((sound*32767).astype('<i2').tobytes())
            classic = analyze_track(source)
            bundle = DEFAULT_PIPELINE.analyse(source)
            for engine in ('M2Pv1', 'M2Pv2'):
                for scheme in COLOR_SCHEMES:
                    options = RenderOptions(engine=engine, size=192, color_scheme=scheme, colors=('#112233','#EEAA88'))
                    image = render_with_options(source, options, classic_analysis=classic, bundle=bundle)
                    assert image.size == (192,192)
                    report['checks'].append(f'{engine}/{scheme}')
            root = tk.Tk()
            root.withdraw()
            app = Playground(root)
            root.update_idletasks()
            app.automatic.set(False)
            app.path.set(str(source))
            app.size.set('256')
            for engine in ('M2Pv1','M2Pv2'):
                app.engine.set(engine)
                app.preview()
                deadline = time.monotonic()+30
                while app.busy and time.monotonic()<deadline:
                    root.update()
                    time.sleep(.01)
                assert not app.busy and app.last_image is not None, app.status.get()
                assert app.last_image.size == (256,256)
                report['checks'].append(f'GUI preview {engine}')
            app._start('save', str(Path(directory)/'export.png'))
            deadline = time.monotonic()+30
            while app.busy and time.monotonic()<deadline:
                root.update()
                time.sleep(.01)
            assert (Path(directory)/'export.png').is_file(), app.status.get()
            assert (Path(directory)/'.m2p/export.profile.json').is_file()
            report['checks'].append('GUI PNG export and profile')
            app.close()
        report['ok'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report['ok']
