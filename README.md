# Music2Picture v2

[English](#english)

Music2Picture v2 анализирует музыкальный файл и создаёт квадратную обложку через единый адаптивный параметрический движок. Отдельные режимы Aurora, Plasma, Ocean и Fusion удалены: геометрия, палитра, фактура, плотность, фокус и движение теперь непрерывно вычисляются для конкретной песни.

## Пайплайн

```text
Audio
-> Audio Analysis
-> VisualDNA
-> Song Description
-> Visual Brief + VisualPlan
-> Music2Picture v2 Cover
```

Анализ сохраняет раздельно:

- абсолютную громкость, пик и crest factor;
- относительную и структурную динамику;
- темп, уверенность, атаки, плотность и регулярность ритма;
- спектральный центр, rolloff, contrast, flatness, flux и zero crossing rate;
- басовую массу, гармоничность, тональность, лад и смены гармонии;
- части песни, контраст секций, положение перехода и кульминации.

Название и внешние метаданные могут уточнять описание, но звук остаётся основной частью `VisualDNA`. Палитра не определяется одним BPM или одним жанром.

## Одна песня

```powershell
python .\music2picture.py covers --source "C:\Music\song.mp3" --output "C:\Music\covers" --seed 42
```

Текст на изображении по умолчанию выключен. Добавить имя файла после рендеринга:

```powershell
python .\music2picture.py covers --source "C:\Music\song.mp3" --output "C:\Music\covers" --center-title
```

## Папка и отдельные описания

```powershell
python .\music2picture.py covers --source "C:\Music\Input" --output "C:\Music\covers"
python .\music2picture.py describe --source "C:\Music\Input" --output "C:\Music\descriptions"
```

Для каждого файла создаются собственные `song_description` и `visual_brief`. Результат привязывается к нормализованному пути, размеру, времени изменения и аудио-отпечатку. Неизменённые файлы восстанавливаются из `%LOCALAPPDATA%\SonicForge\analysis\track_descriptions.json`. Ошибка одного трека не останавливает папку; `--regenerate` принудительно обновляет тексты.

## Python API

```python
from music2picture import make_cover, make_covers, describe

make_cover("song.mp3", "cover.png", size=1000, seed=42)
make_covers("music", "covers", size=1000)
describe("music", output="descriptions")
```

Старые именованные аргументы принимаются для совместимости, но больше не выбирают шаблон или цветовой режим.

## Установка

```powershell
pip install -r requirements.txt
```

FFmpeg и FFprobe должны быть доступны в `PATH`.

## Основа решений

- [Essentia descriptors](https://essentia.upf.edu/documentation.html)
- [DEAM valence/arousal dataset](https://cvml.unige.ch/databases/DEAM/)
- [Music-color associations are mediated by emotion](https://doi.org/10.1073/pnas.1212562110)
- [MuLan audio-language representation](https://arxiv.org/abs/2208.12415)
- [CLAP audio-language representation](https://arxiv.org/abs/2206.04769)
- [Audio-guided Album Cover Art Generation](https://arxiv.org/abs/2207.07162)

Текущая версия использует компактный анализ NumPy/SciPy. MuLan и CLAP приведены как направление для будущего обучаемого audio-text слоя, а не как уже встроенные модели.

> Автор проекта: Зейналов У.Р.о.

---

## English

Music2Picture v2 analyzes music and creates square cover art through one universal adaptive parametric renderer. The former Aurora, Plasma, Ocean, and Fusion modes have been removed. Geometry, palette, texture, density, focal balance, and motion are continuously derived from each track's `VisualDNA` and `VisualPlan`.

The text-first pipeline is:

```text
Audio -> Audio Analysis -> VisualDNA -> Song Description
-> Visual Brief + VisualPlan -> Music2Picture v2 Cover
```

Absolute loudness is kept separate from local dynamics and global structure. Rhythm, attacks, spectral descriptors, bass mass, harmony, key, section contrast, and climax position all contribute to the result. There is no direct BPM-to-color rule.

Batch description generation creates an independent `song_description` and `visual_brief` for every track. Persistent records use canonical path, file size, modification time, and an audio fingerprint. A damaged file is reported without stopping the remaining batch.

```powershell
pip install -r requirements.txt
python .\music2picture.py covers --source "C:\Music\song.mp3" --output "C:\Music\covers"
python .\music2picture.py describe --source "C:\Music\Input" --output "C:\Music\descriptions"
```

FFmpeg and FFprobe must be available in `PATH`. Rendering is deterministic when `--seed` is supplied, and cover text is disabled by default.
