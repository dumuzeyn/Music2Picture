# Music2Picture 2.2.0 — M2Pv1 + M2Pv2 + M2Pv3 Studio

## Русский

- M2Pv3 доступен в M2P-Studio рядом с M2Pv1 и M2Pv2, а также в Python API и CLI.
- Органическая фактура M2Pv2 дополнена спектральной структурой и динамикой песни. Начало расположено слева, конец — справа; развитие песни влияет на оттенки, движение и плотность фактуры.
- Включена актуальная версия M2Pv3 из SonicForge: мягкие изогнутые переходы вместо прямых полос, более заметный органический узор.
- Для M2Pv3 доступны Seed, палитры, композиция, настроение, детализация, контраст, насыщенность, мягкость и размер экспорта. PNG сопровождается JSON-профилем с версией генератора и направлением времени.
- Спектральный анализ кэшируется с проверкой размера и времени изменения исходника. Короткие записи и тишина обрабатываются без выдуманной ритмической активности.
- Python-модуль `music2picture_v3.colors.apply_speed_colors` предоставляет окраску по измеренной скорости ритма; готовые палитры Studio остаются доступны.

**M2P-Studio.exe** — приложение Windows x64. Для чтения аудио нужен внешний **FFmpeg**: добавьте его в PATH или поместите ffmpeg.exe и ffprobe.exe в папку tools рядом с приложением. FFmpeg не входит в EXE.

**Music2Picture-2.2.0-source.zip** — исходники этой версии. **SHA256SUMS.txt** — контрольные суммы. Предпросмотр и сохранение PNG не изменяют аудиофайл.

## English

- M2P-Studio now includes M2Pv3 alongside M2Pv1 and M2Pv2; M2Pv3 is also available through the Python API and CLI.
- M2Pv2 organic surfaces incorporate spectral structure and song dynamics. The opening is on the left and the ending on the right; song development guides color, movement and texture density.
- Includes the current SonicForge M2Pv3 renderer, with softly curved transitions instead of straight stripes and stronger organic detail.
- M2Pv3 supports Seed, palettes, composition, mood, detail, contrast, saturation, softness and export size. PNG exports include a JSON settings profile with generator version and timeline direction.
- Spectral analysis is cached by source path, size and modification time. Short recordings and silence avoid invented rhythmic activity.
- The Python module `music2picture_v3.colors.apply_speed_colors` provides measured rhythmic-speed coloring; Studio's existing palettes remain available.

Downloads: **M2P-Studio.exe**, **Music2Picture-2.2.0-source.zip**, **SHA256SUMS.txt**.
The Windows x64 EXE requires external **FFmpeg**, either in PATH or as ffmpeg.exe and ffprobe.exe in a tools folder beside the EXE. FFmpeg is not bundled. Preview and PNG export do not modify source audio.
