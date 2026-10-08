"""Generate README illustrations from original synthetic audio, not user songs."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from m2p_controls import RenderOptions, render_with_options
from music2picture_v1 import analyze_track
from music2picture_v2 import DEFAULT_PIPELINE


def synthetic(path, driven):
    rate = 22050
    t = np.arange(rate * 24, dtype=np.float32) / rate
    pad = (np.sin(2*np.pi*110*t)*.10 + np.sin(2*np.pi*165*t)*.07 + np.sin(2*np.pi*220*t)*.055)
    if driven:
        phase = np.mod(t, 60/142)
        kick = np.sin(2*np.pi*(70*t - 12*np.exp(-phase*30))) * np.exp(-phase*23)*.58
        rng = np.random.default_rng(91)
        hats = rng.normal(0,.12,len(t))*np.exp(-np.mod(t,60/284)*95)
        pulse = np.sin(2*np.pi*660*t)*(.035+.065*(np.mod(t,60/142)<.12))
        audio = pad*.9 + kick + hats + pulse
    else:
        audio = pad*(.65+.18*np.sin(t*.45)) + np.sin(2*np.pi*330*t)*.028
    fade = np.minimum(np.minimum(t/.8,(24-t)/.8),1)
    audio = np.clip(audio*fade,-.98,.98)
    with wave.open(str(path),'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes((audio*32767).astype('<i2').tobytes())


def sheet(images, labels, columns, target, tile=320):
    rows = (len(images)+columns-1)//columns
    result = Image.new('RGB',(columns*tile,rows*(tile+32)),'#f4f4fa')
    draw = ImageDraw.Draw(result)
    path = Path('C:/Windows/Fonts/segoeui.ttf')
    font = ImageFont.truetype(str(path),18) if path.exists() else ImageFont.load_default()
    for index,(image,label) in enumerate(zip(images,labels)):
        x,y=(index%columns)*tile,(index//columns)*(tile+32)
        draw.text((x+8,y+5),label,fill='#292938',font=font)
        result.paste(image.resize((tile,tile),Image.Resampling.LANCZOS),(x,y+32))
    result.save(target,'PNG',optimize=True)


def main():
    output = ROOT/'docs/images'
    output.mkdir(parents=True,exist_ok=True)
    (ROOT/'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='synthetic-examples-',dir=ROOT/'build') as temporary:
        tracks=[]
        for driven in (False,True):
            path=Path(temporary)/('driven.wav' if driven else 'calm.wav')
            synthetic(path,driven)
            tracks.append((path,analyze_track(path),DEFAULT_PIPELINE.analyse(path)))
        images=[]
        labels=[]
        for index,(path,classic,bundle) in enumerate(tracks):
            for engine in ('M2Pv1','M2Pv2'):
                options=RenderOptions(engine=engine,size=640,seed=42)
                images.append(render_with_options(path,options,classic_analysis=classic,bundle=bundle))
                labels.append(f'{engine}: '+('driven' if index else 'calm'))
        sheet(images,labels,2,output/'engines.png')
        path,classic,bundle=tracks[1]
        images=[render_with_options(path,RenderOptions(engine='M2Pv1',size=640,seed=42,color_mode=mode),
                  classic_analysis=classic) for mode in ('ocean','plasma','fusion','aurora')]
        sheet(images,['Ocean','Plasma','Fusion','Aurora'],2,output/'m2pv1-modes.png')
        schemes=('auto','sunset','ocean','neon','forest','mono')
        images=[render_with_options(path,RenderOptions(size=640,seed=42,color_scheme=scheme),bundle=bundle) for scheme in schemes]
        sheet(images,['Auto','Sunset','Ocean','Neon','Forest','Monochrome'],3,output/'color-schemes.png',tile=256)
    print('Created three README sheets from synthetic sound.')


if __name__=='__main__':
    main()
