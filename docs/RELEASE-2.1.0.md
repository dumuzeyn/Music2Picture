# Music2Picture 2.1.0 — M2Pv1 + M2Pv2 Studio

## Русский

- M2Pv1: классический движок с Ocean, Plasma, Fusion и Aurora. Исправление зернистости сохраняет прежнюю геометрию и тонкие контуры.
- M2Pv2: актуальный современный органический генератор. Основной характер управляет рисунком и диапазоном палитры; противоположные секции дают слабые контурные акценты.
- Windows EXE **M2P-Studio.exe**: выбор песни/движка, редактируемые Seed, детализация, размер, композиция, настроение, контраст, насыщенность и мягкость; автообновление предпросмотра и PNG-экспорт.
- Палитры: автоматическая, Закат, Океан, Неон, Лес, Монохром; свои цвета без фиксированного лимита.
- Неизменённый анализ переиспользуется, рендер последовательный в рабочем потоке. GUI не изменяет музыку/метаданные.
- Подробный единый RU/EN README: отдельные Mermaid-схемы музыки → картинки для обоих поколений, признаки, формы, палитры, настройки и ограничения.
- Python API/CLI выбирают `--engine M2Pv1` / `M2Pv2`. Явное MP3-встраивание сохраняет существующий текст и аудиобайты.

### Файлы

- **M2P-Studio.exe** — неподписанный Windows x64 EXE; Python не нужен. Требуется внешний FFmpeg в PATH либо `tools/ffmpeg.exe` рядом с EXE. GUI на русском.
- **Music2Picture-2.1.0-source.zip** — исходники, тесты, README, иллюстрации и скрипт сборки.
- **SHA256SUMS.txt** — контрольные суммы.

FFmpeg не включён. GUI экспортирует только PNG; нормализация и изменение MP3 — отдельные явно выбранные CLI-операции. M2Pv1/M2Pv2 — поколения алгоритма, 2.1.0 — версия пакета, не релиз SonicForge.

## English

- Restored **M2Pv1** classic modes with edge-preserving cleanup and original warp geometry.
- Current **M2Pv2** organic rendering, character-selected palette ranges and restrained contour accents for contrasting sections.
- **M2P-Studio.exe**: Windows playground with editable Seed, detail, size, composition, mood, contrast, saturation, softness, automatic preview and PNG export.
- Automatic, Sunset, Ocean, Neon, Forest, Monochrome and unlimited-count custom palettes.
- Reused unchanged analysis, sequential background rendering and a read-only GUI workflow.
- Detailed bilingual README with separate Mermaid formation diagrams, source links, controls and limitations.
- Explicit MP3 artwork updates retain existing lyrics, other ID3 frames and audio bytes.

Assets: **M2P-Studio.exe**, **Music2Picture-2.1.0-source.zip**, **SHA256SUMS.txt**. Python is unnecessary for the EXE; external FFmpeg is required in PATH or `tools` next to it. GUI labels are Russian. The EXE is unsigned; verify checksums without disabling Windows protection. FFmpeg is not bundled.

M2Pv1/M2Pv2 are algorithm generations; 2.1.0 is the package release, not a SonicForge release.
