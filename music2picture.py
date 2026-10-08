from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageDraw, ImageFont

from music2picture_v2 import DEFAULT_PIPELINE, DescriptionStore, audio_files, generate_descriptions, render_cover
from m2p_controls import RenderOptions, VERSION, ENGINES, COLOR_SCHEMES, MOODS, parse_colors, render_with_options
from music2picture_v2.renderer import COMPOSITIONS


STARTUP_KWARGS = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def require_ffmpeg():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and FFprobe are required")


def make_cover(
    audio_path,
    output_path,
    size=1000,
    patterns=2,
    center_title=False,
    seed=None,
    analysis_bundle=None,
    engine='M2Pv2',
    detail=None,
    color_mode='plasma',
    color_scheme='auto',
    colors=(),
    contrast=100,
    saturation=100,
    softness=0,
    mood='auto',
    composition='auto',
    **_deprecated,
):
    """Create M2Pv1 or M2Pv2 artwork; the source is unchanged by this function."""
    options = RenderOptions(engine=engine, size=size, seed=0 if seed is None else seed,
                            detail=detail, color_mode=color_mode, patterns=patterns,
                            color_scheme=color_scheme, colors=tuple(colors), contrast=contrast,
                            saturation=saturation, softness=softness, mood=mood,
                            composition=composition, center_title=center_title).validated()
    require_ffmpeg()
    path = Path(audio_path).resolve()
    output_path = Path(output_path)
    if output_path.resolve() == path:
        raise ValueError('A cover cannot overwrite its source audio')
    bundle = None if engine == 'M2Pv1' else analysis_bundle or DEFAULT_PIPELINE.analyse(
        path,
        metadata={"title": path.stem},
        mood_override=mood,
        progress=lambda stage: print(stage.replace("_", " ").capitalize()),
    )
    if bundle is not None:
        DescriptionStore().put(path, bundle)
    image = render_with_options(path, options, bundle=bundle)
    if center_title:
        _draw_optional_title(image, path.stem)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG", optimize=True)
    _save_profile(output_path, path, bundle, seed, center_title, options=options)
    print(f"Cover saved: {output_path}")
    return output_path


def make_covers(source, output, size=1000, embed=False, seed=None, center_title=False, **kwargs):
    source_path = Path(source).resolve()
    source_base = source_path.parent if source_path.is_file() else source_path
    output = Path(output).resolve()
    files = audio_files(source_path)
    if not files:
        raise RuntimeError(f"No supported audio files found in {source_path}")
    results = []
    errors = []
    for index, path in enumerate(files, start=1):
        relative = path.relative_to(source_base).with_suffix("")
        target = output / relative.parent / f"{relative.name}_cover_{size}.png"
        print(f"[{index}/{len(files)}] {path.name}")
        try:
            cover = make_cover(
                path,
                target,
                size=size,
                seed=None if seed is None else int(seed) + index - 1,
                center_title=center_title,
                **kwargs,
            )
            if embed:
                embed_cover(path, cover)
            results.append(cover)
        except Exception as exc:
            errors.append((path, str(exc)))
            print(f"Error for {path.name}: {exc}")
            if len(files) == 1:
                raise
    print(f"Completed: {len(results)}; errors: {len(errors)}")
    return results


def describe(source, output=None, regenerate=False):
    results = generate_descriptions(
        source,
        regenerate=regenerate,
        progress=lambda index, total, path, stage: print(f"[{index}/{total}] {path.name}: {stage}"),
    )
    if output:
        records = [
            {
                "path": str(item.path),
                "status": item.status,
                "fingerprint": item.fingerprint,
                "song_description": item.song_description,
                "visual_brief": item.visual_brief,
                "error": item.error,
            }
            for item in results
        ]
        DescriptionStore().export(records, Path(output) / "track_descriptions.json")
    return results


def normalize_music(source, output, integrated_lufs=-14.0, true_peak=-1.5, lra=11.0, final_gain=1.0):
    """Retain the previous normalization entry point for existing users."""
    require_ffmpeg()
    source_path = Path(source).resolve()
    source_base = source_path.parent if source_path.is_file() else source_path
    output = Path(output).resolve()
    for path in audio_files(source_path):
        relative = path.relative_to(source_base).with_suffix(".mp3")
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        loudnorm = f"loudnorm=I={integrated_lufs}:TP={true_peak}:LRA={lra},volume={final_gain}"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-vn", "-af", loudnorm, "-c:a", "libmp3lame", "-q:a", "0", str(target)],
            check=True,
            **STARTUP_KWARGS,
        )


def embed_cover(mp3_path, image_path):
    mp3_path = Path(mp3_path)
    if mp3_path.suffix.lower() != ".mp3":
        return False
    from m2p_id3 import ID3Frame, update_id3
    from PIL import Image
    image_path = Path(image_path)
    if image_path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('Cover exceeds the supported ID3 size')
    with Image.open(image_path) as image:
        image.verify()
        mime = {'PNG': b'image/png', 'JPEG': b'image/jpeg'}.get(image.format)
    if mime is None:
        raise ValueError('Embedded cover must be PNG or JPEG')
    update_id3(mp3_path, [ID3Frame('APIC', b'\x00' + mime + b'\x00\x03\x00' + image_path.read_bytes())], remove_names=('APIC',))
    return True


def _draw_optional_title(image, title):
    draw = ImageDraw.Draw(image)
    font_path = Path("C:/Windows/Fonts/seguisb.ttf")
    font = ImageFont.truetype(str(font_path), max(18, image.width // 16)) if font_path.exists() else ImageFont.load_default()
    text = title
    lines = []
    current = ''
    for word in text.split():
        candidate = f'{current} {word}'.strip()
        if current and draw.textlength(candidate, font=font) > image.width * .86:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)
    text = '\n'.join(lines)
    # Reduce only when an unbroken word really cannot fit; never truncate titles.
    if font_path.exists():
        while font.size > 10 and max(draw.textlength(line, font=font) for line in lines) > image.width * .90:
            font = ImageFont.truetype(str(font_path), font.size - 1)
    stroke = max(1, image.width // 450)
    box = draw.multiline_textbbox((0, 0), text, font=font, spacing=4, stroke_width=stroke)
    x = (image.width - (box[2] - box[0])) / 2 - box[0]
    y = (image.height - (box[3] - box[1])) / 2 - box[1]
    draw.multiline_text((x, y), text, font=font, fill='white', align='center', spacing=4,
                       stroke_width=stroke, stroke_fill='black')


def _save_profile(output_path, audio_path, bundle, seed, center_title, options=None):
    directory = output_path.parent / ".m2p"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{output_path.stem}.profile.json"
    data = {
        "engine": options.engine if options else 'M2Pv2',
        'release_version': VERSION,
        "audio_path": str(audio_path),
        "seed": seed,
        "title_added": bool(center_title),
        "analysis_bundle": bundle.to_dict() if bundle else None,
        'settings': options.to_dict() if options else {},
    }
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    if len(sys.argv) == 1:
        from m2p_gui import main as gui_main
        gui_main()
        return
    parser = argparse.ArgumentParser(description="M2Pv1 + M2Pv2: music-to-picture generators")
    parser.add_argument('--version', action='version', version=f'Music2Picture {VERSION}')
    commands = parser.add_subparsers(dest="command", required=True)
    covers = commands.add_parser("covers")
    covers.add_argument("--source", required=True)
    covers.add_argument("--output", required=True)
    covers.add_argument("--size", type=int, default=1000)
    covers.add_argument("--seed", type=int)
    covers.add_argument("--center-title", action="store_true", help="Add the filename after rendering. Disabled by default.")
    covers.add_argument("--embed-cover", action="store_true")
    covers.add_argument('--engine', choices=ENGINES, default='M2Pv2')
    covers.add_argument('--detail', type=float)
    covers.add_argument('--patterns', type=int, choices=(1, 2), default=2)
    covers.add_argument('--color-mode', choices=('ocean', 'plasma', 'fusion', 'aurora'), default='plasma')
    covers.add_argument('--color-scheme', choices=COLOR_SCHEMES, default='auto')
    covers.add_argument('--colors', default='', help='Custom #RRGGBB colors, separated by commas')
    covers.add_argument('--contrast', type=float, default=100)
    covers.add_argument('--saturation', type=float, default=100)
    covers.add_argument('--softness', type=float, default=0)
    covers.add_argument('--mood', choices=MOODS, default='auto')
    covers.add_argument('--composition', choices=('auto', *COMPOSITIONS), default='auto')
    commands.add_parser('gui', help='Open the interactive desktop playground')
    descriptions = commands.add_parser("describe")
    descriptions.add_argument("--source", required=True)
    descriptions.add_argument("--output")
    descriptions.add_argument("--regenerate", action="store_true")
    process = commands.add_parser("process")
    process.add_argument("--source", required=True)
    process.add_argument("--output", required=True)
    process.add_argument("--integrated-lufs", type=float, default=-14.0)
    process.add_argument("--true-peak", type=float, default=-1.5)
    process.add_argument("--lra", type=float, default=11.0)
    process.add_argument("--final-gain", type=float, default=1.0)
    args = parser.parse_args()
    if args.command == "covers":
        make_covers(args.source, args.output, size=args.size, seed=args.seed, center_title=args.center_title, embed=args.embed_cover,
                    engine=args.engine, detail=args.detail, patterns=args.patterns, color_mode=args.color_mode,
                    color_scheme=args.color_scheme, colors=parse_colors(args.colors), contrast=args.contrast,
                    saturation=args.saturation, softness=args.softness, mood=args.mood, composition=args.composition)
    elif args.command == "describe":
        describe(args.source, output=args.output, regenerate=args.regenerate)
    elif args.command == 'process':
        normalize_music(args.source, args.output, args.integrated_lufs, args.true_peak, args.lra, args.final_gain)
    else:
        from m2p_gui import main as gui_main
        gui_main()


if __name__ == "__main__":
    main()
