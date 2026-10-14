"""Shared validated controls for the Python API, CLI and desktop playground."""
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import ImageEnhance, ImageFilter

from music2picture_v2.custom_style import CustomCoverSettings, palette_rgb
from music2picture_v2.renderer import COMPOSITIONS

VERSION = '2.2.0'
ENGINES = ('M2Pv1', 'M2Pv2', 'M2Pv3')
COLOR_SCHEMES = {
    'auto': (),
    'sunset': ('#25143B', '#64365E', '#AE4663', '#EE6A53', '#FFC078'),
    'ocean': ('#0B1639', '#173B69', '#226B8F', '#36B6BA', '#BCEEE0'),
    'neon': ('#160F36', '#45238F', '#9F30C6', '#F347A8', '#FFD261'),
    'forest': ('#0D201F', '#1B4837', '#44805A', '#90B067', '#E8CB7F'),
    'mono': ('#101018', '#343442', '#666674', '#ACACB8', '#F0F0F5'),
    'custom': (),
}
MOODS = ('auto', 'calm', 'melancholic', 'energetic', 'intense', 'romantic')


@dataclass(frozen=True)
class RenderOptions:
    engine: str = 'M2Pv2'
    size: int = 1000
    seed: int = 0
    detail: float | None = None
    color_mode: str = 'plasma'
    patterns: int = 2
    color_scheme: str = 'auto'
    colors: tuple[str, ...] = ()
    contrast: float = 100
    saturation: float = 100
    softness: float = 0
    mood: str = 'auto'
    composition: str = 'auto'
    center_title: bool = False

    def validated(self):
        if self.engine not in ENGINES:
            raise ValueError('Choose M2Pv1, M2Pv2 or M2Pv3')
        if isinstance(self.size, bool) or not isinstance(self.size, int) or not 64 <= self.size <= 4096:
            raise ValueError('Size must be an integer from 64 to 4096')
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed <= 2**31 - 1:
            raise ValueError('Seed must be an integer from 0 to 2147483647')
        if self.color_mode not in ('ocean', 'plasma', 'fusion', 'aurora') or self.patterns not in (1, 2):
            raise ValueError('Invalid M2Pv1 color mode or pattern count')
        if self.color_scheme not in COLOR_SCHEMES or self.mood not in MOODS:
            raise ValueError('Unknown palette or mood')
        if self.composition not in ('auto', *COMPOSITIONS):
            raise ValueError('Unknown M2Pv2/M2Pv3 composition')
        if self.color_scheme == 'custom' and not self.colors:
            raise ValueError('Custom palette needs at least one #RRGGBB color')
        CustomCoverSettings.parse({
            'colors': self.palette or ('#6551C7',),
            'detail': 50 if self.detail is None else self.detail,
            'contrast': self.contrast, 'saturation': self.saturation, 'softness': self.softness})
        return self

    @property
    def palette(self):
        return self.colors if self.color_scheme == 'custom' else COLOR_SCHEMES[self.color_scheme]

    def to_dict(self):
        return asdict(self)


def parse_colors(text):
    return tuple(item.strip() for item in text.split(',') if item.strip())


def finish_image(image, options):
    image = ImageEnhance.Contrast(image).enhance(options.contrast / 100)
    image = ImageEnhance.Color(image).enhance(options.saturation / 100)
    if options.softness:
        image = image.filter(ImageFilter.GaussianBlur(image.width * .008 * options.softness / 100))
    return image


def render_with_options(path, options=None, *, bundle=None, classic_analysis=None, song_structure=None, preview=False):
    path = Path(path).resolve()
    options = (options or RenderOptions()).validated()
    if options.engine == 'M2Pv1':
        from music2picture_v1 import render_classic
        image = render_classic(path, size=options.size, seed=options.seed,
                               color_mode=options.color_mode, patterns=options.patterns,
                               detail=options.detail, analysis=classic_analysis)
        if options.palette:
            import numpy as np
            from PIL import Image, ImageOps
            gray = ImageOps.autocontrast(image.convert('L'), cutoff=1)
            lookup = palette_rgb(options.palette, np.arange(256, dtype=np.float32) / 255)
            image = Image.fromarray(lookup[np.asarray(gray)], 'RGB')
    else:
        from music2picture_v2 import DEFAULT_PIPELINE, render_cover
        bundle = bundle or DEFAULT_PIPELINE.analyse(path, metadata={'title': path.stem}, mood_override=options.mood)
        extra = {}
        if options.engine == 'M2Pv3':
            from music2picture_v3 import analyze_structure, render_cover
            extra['structure'] = song_structure if song_structure is not None else analyze_structure(path)
        image = render_cover(bundle.visual_dna, bundle.visual_plan, size=options.size, seed=options.seed,
                             preview=preview, detail=options.detail, palette=options.palette or None,
                             composition=None if options.composition == 'auto' else options.composition, **extra)
    return finish_image(image, options)
