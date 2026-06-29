# Music2Picture

Music2Picture создает квадратные PNG-обложки из аудиофайлов. Картинка строится по спектру, громкости, басу, верхам, локальной энергии и BPM песни. Название трека рисуется по центру по умолчанию.

Основной файл:

```text
music2picture.py
```

## Возможности

- Генерация обложек `1000x1000` для одного трека или папки с музыкой.
- Четыре режима цвета и характера: `Ocean`, `Plasma`, `Fusion`, `Aurora`.
- Короткие алиасы режимов: `O`, `D`, `F`, `A`.
- Повторяемый результат через `--seed`.
- Текст по центру включен по умолчанию.
- Опциональное встраивание PNG как обложки MP3 через FFmpeg.

## Режимы

| Режим | Алиас | Что делает |
|---|---:|---|
| `Ocean` | `O` | Цвет строится от BPM и музыкального движения. Это бывший `bpm`. |
| `Plasma` | `D` | Энергичный режим с диагональным движением и контрастными акцентами. Это бывший `drive`. |
| `Fusion` | `F` | Органический режим по характеру песни: энергия, бас, середина, верха. Это бывший `character`. |
| `Aurora` | `A` | Основан на `Fusion`, но добавляет мягкие северные переливы и световые ленты. |

Старые имена `bpm`, `drive`, `character` все еще принимаются как совместимые алиасы.

## Пример режимов

Одна случайно выбранная песня из коллекции: `Космический цветок.mp3`.

| Ocean | Plasma |
|---|---|
| ![Ocean](example/modes/kosmicheskiy-cvetok_ocean.png) | ![Plasma](example/modes/kosmicheskiy-cvetok_plasma.png) |

| Fusion | Aurora |
|---|---|
| ![Fusion](example/modes/kosmicheskiy-cvetok_fusion.png) | ![Aurora](example/modes/kosmicheskiy-cvetok_aurora.png) |

## Установка

Нужны Python-зависимости:

```powershell
pip install numpy pillow
```

Также нужен FFmpeg и FFprobe в `PATH`:

```powershell
ffmpeg -version
ffprobe -version
```

## Генерация

Сгенерировать обложку для одного файла:

```powershell
python .\music2picture.py covers --source "C:\Music\song.mp3" --output "C:\Music\covers" --color-mode aurora --seed 42
```

Сгенерировать обложки для всей папки:

```powershell
python .\music2picture.py covers --source "C:\Music\Input" --output "C:\Music\covers" --color-mode plasma --seed 42
```

Использовать короткий алиас режима:

```powershell
python .\music2picture.py covers --source "C:\Music\song.mp3" --output "C:\Music\covers" --color-mode A
```

Сгенерировать без текста:

```powershell
python .\music2picture.py covers --source "C:\Music\song.mp3" --output "C:\Music\covers" --no-center-title
```

Встроить картинку как обложку MP3:

```powershell
python .\music2picture.py covers --source "C:\Music\song.mp3" --output "C:\Music\covers" --embed-cover
```

## Текст

Текст включен по умолчанию. Используется имя файла без расширения.

Особенности текста:

- автоматический перенос слов на несколько строк;
- центрирование всего блока надписи по центру картинки;
- единая тень в одном направлении;
- большая часть букв остается белой;
- внутри букв могут появляться редкие рваные фрагменты цвета фона.

## Настройки из кода

Можно включить запуск прямо из файла:

```python
RUN_FROM_CODE = True
CODE_MODE = "covers"
CODE_SOURCE = r"C:\Music\song.mp3"
CODE_OUTPUT = r"C:\Music\covers"
CODE_COLOR_MODE = "aurora"
CODE_CENTER_TITLE = True
CODE_SEED = 42
```

## Команды CLI

```text
process  - нормализация музыки через FFmpeg
covers   - генерация PNG-обложек
```

Основные параметры `covers`:

```text
--source          файл или папка с музыкой
--output          папка для PNG
--size            размер изображения, по умолчанию 1000
--patterns        1 или 2, богатство узора
--color-mode      ocean/plasma/fusion/aurora или O/D/F/A
--seed            фиксирует случайность
--center-title    текст по центру, включен по умолчанию
--no-center-title отключает текст
--embed-cover     встроить PNG в MP3
```
