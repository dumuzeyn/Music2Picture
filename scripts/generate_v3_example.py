"""Compare global organic artwork with the chronological engine on synthetic sound."""
from pathlib import Path
import sys
import wave

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from m2p_controls import RenderOptions, render_with_options
from music2picture_v2 import DEFAULT_PIPELINE
from generate_examples import sheet


def main():
    output = ROOT / 'docs/images'
    output.mkdir(parents=True, exist_ok=True)
    (ROOT / 'build').mkdir(exist_ok=True)
    source = ROOT / 'build/v3-synthetic.wav'
    rate = 22050
    t = np.arange(rate * 48) / rate
    pad = np.sin(2 * np.pi * 110 * t) * .10 + np.sin(2 * np.pi * 165 * t) * .07
    phase = np.mod(t, 60 / 142)
    kick = np.sin(2 * np.pi * (70 * t - 12 * np.exp(-phase * 30))) * np.exp(-phase * 23) * .58
    hats = np.random.default_rng(91).normal(0, .15, len(t)) * np.exp(-np.mod(t, 60 / 284) * 95)
    intensity = np.interp(t, (0, 10, 16, 30, 36, 48), (0, 0, 1, 1, 0, 0))
    audio = pad * (.5 + intensity * .5) + (kick + hats) * intensity
    audio *= np.minimum(np.minimum(t / .8, (48 - t) / .8), 1)
    with wave.open(str(source), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes((np.clip(audio, -.98, .98) * 32767).astype('<i2').tobytes())
    bundle = DEFAULT_PIPELINE.analyse(source)
    images = [render_with_options(source, RenderOptions(engine=engine, size=1000, seed=42,
                  color_scheme='sunset'), bundle=bundle) for engine in ('M2Pv2', 'M2Pv3')]
    images[1].save(output / 'm2pv3-timeline.png', optimize=True)
    sheet(images, ['M2Pv2: overall character', 'M2Pv3: intro > build > drive > outro'],
          2, output / 'm2pv3-comparison.png', tile=500)
    print('Created M2Pv3 timeline and comparison from synthetic sound.')


if __name__ == '__main__':
    main()
