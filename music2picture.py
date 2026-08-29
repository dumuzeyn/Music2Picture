from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageDraw, ImageFont

from music2picture_v2 import DEFAULT_PIPELINE, DescriptionStore, audio_files, generate_descriptions, render_cover


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
    **_deprecated,
):
    """Create one cover with the universal Music2Picture v2 renderer.

    ``patterns`` and unknown legacy keyword arguments are accepted only so old
    integrations keep running; they no longer select a visual template.
    """
    del patterns
    require_ffmpeg()
    path = Path(audio_path).resolve()
    output_path = Path(output_path)
    bundle = analysis_bundle or DEFAULT_PIPELINE.analyse(
        path,
        metadata={"title": path.stem},
        progress=lambda stage: print(stage.replace("_", " ").capitalize()),
    )
    DescriptionStore().put(path, bundle)
    image = render_cover(bundle.visual_dna, bundle.visual_plan, size=size, seed=seed)
    if center_title:
        _draw_optional_title(image, path.stem)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG", optimize=True)
    _save_profile(output_path, path, bundle, seed, center_title)
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
    temporary = mp3_path.with_name(f"{mp3_path.stem}.cover_tmp.mp3")
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(mp3_path), "-i", str(image_path),
            "-map", "0:a:0", "-map", "1:v:0", "-c:a", "copy", "-c:v", "mjpeg", "-disposition:v:0", "attached_pic",
            "-map_metadata", "0", "-id3v2_version", "3", str(temporary),
        ],
        check=True,
        **STARTUP_KWARGS,
    )
    temporary.replace(mp3_path)
    return True


def _draw_optional_title(image, title):
    draw = ImageDraw.Draw(image)
    font_path = Path("C:/Windows/Fonts/seguisb.ttf")
    font = ImageFont.truetype(str(font_path), max(18, image.width // 16)) if font_path.exists() else ImageFont.load_default()
    text = title[:60]
    box = draw.textbbox((0, 0), text, font=font, stroke_width=2)
    x = (image.width - (box[2] - box[0])) / 2
    y = image.height * 0.82
    draw.text((x, y), text, font=font, fill="white", stroke_width=max(1, image.width // 450), stroke_fill="black")


def _save_profile(output_path, audio_path, bundle, seed, center_title):
    directory = output_path.parent / ".sonicforge"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{output_path.stem}.profile.json"
    data = {
        "engine": "Music2Picture v2",
        "audio_path": str(audio_path),
        "seed": seed,
        "title_added": bool(center_title),
        "analysis_bundle": bundle.to_dict(),
    }
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Music2Picture v2 audio analysis and adaptive cover renderer")
    commands = parser.add_subparsers(dest="command", required=True)
    covers = commands.add_parser("covers")
    covers.add_argument("--source", required=True)
    covers.add_argument("--output", required=True)
    covers.add_argument("--size", type=int, default=1000)
    covers.add_argument("--seed", type=int)
    covers.add_argument("--center-title", action="store_true", help="Add the filename after rendering. Disabled by default.")
    covers.add_argument("--embed-cover", action="store_true")
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
        make_covers(args.source, args.output, size=args.size, seed=args.seed, center_title=args.center_title, embed=args.embed_cover)
    elif args.command == "describe":
        describe(args.source, output=args.output, regenerate=args.regenerate)
    else:
        normalize_music(args.source, args.output, args.integrated_lufs, args.true_peak, args.lra, args.final_gain)


if __name__ == "__main__":
    main()
