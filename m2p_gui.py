"""Interactive, read-only music-to-picture playground for Windows and Python."""
from dataclasses import replace
import os
from pathlib import Path
import queue
import random
import shutil
import sys
import threading
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageTk

from m2p_controls import (VERSION, ENGINES, COLOR_SCHEMES, MOODS, RenderOptions,
                          parse_colors, render_with_options)
from music2picture_v2.renderer import COMPOSITIONS

SCHEME_LABELS = {'auto': 'По характеру песни', 'sunset': 'Закат', 'ocean': 'Океан',
                 'neon': 'Неон', 'forest': 'Лес', 'mono': 'Монохром', 'custom': 'Свои цвета'}
COMPOSITION_LABELS = {'auto': 'Автоматически по музыке', 'diagonal_pour': 'Диагональный поток',
                      'vortex_marbling': 'Мраморный вихрь', 'radial_bloom': 'Радиальное раскрытие',
                      'cellular_islands': 'Островки', 'folded_currents': 'Складки и течения'}
MOOD_LABELS = {'auto': 'По музыке', 'calm': 'Спокойнее', 'melancholic': 'Меланхоличнее',
               'energetic': 'Энергичнее', 'intense': 'Напряжённее', 'romantic': 'Романтичнее'}
AUDIO_TYPES = {'.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.opus', '.wma'}


def configure_tools():
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    candidates = (root / 'tools', root)
    for folder in candidates:
        if (folder / 'ffmpeg.exe').is_file():
            os.environ['PATH'] = str(folder) + os.pathsep + os.environ.get('PATH', '')
            break


class Playground:
    def __init__(self, root):
        self.root = root
        root.title(f'Music2Picture {VERSION} — M2Pv1 / M2Pv2 / M2Pv3')
        root.geometry('1080x790')
        root.minsize(960, 730)
        root.configure(background='#f4f4fa')
        style = ttk.Style(root)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('TFrame', background='#f4f4fa')
        style.configure('TLabel', background='#f4f4fa', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10), padding=(9, 6))
        style.configure('Title.TLabel', font=('Segoe UI', 18, 'bold'))
        style.configure('Note.TLabel', foreground='#575777', font=('Segoe UI', 9))
        self.path = tk.StringVar()
        self.engine = tk.StringVar(value='M2Pv2')
        self.seed = tk.StringVar(value='0')
        self.size = tk.StringVar(value='1000')
        self.detail = tk.DoubleVar(value=50)
        self.auto_detail = tk.BooleanVar(value=True)
        self.mode = tk.StringVar(value='plasma')
        self.patterns = tk.StringVar(value='2')
        self.scheme = tk.StringVar(value=SCHEME_LABELS['auto'])
        self.colors = tk.StringVar(value='#25143B, #64365E, #AE4663, #EE6A53, #FFC078')
        self.contrast = tk.DoubleVar(value=100)
        self.saturation = tk.DoubleVar(value=100)
        self.softness = tk.DoubleVar(value=0)
        self.composition = tk.StringVar(value=COMPOSITION_LABELS['auto'])
        self.mood = tk.StringVar(value=MOOD_LABELS['auto'])
        self.title = tk.BooleanVar(value=False)
        self.automatic = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Выберите песню. Генерация и PNG-экспорт не изменяют аудиофайл.')
        self.analysis_text = tk.StringVar(value='Параметры объясняются под каждым блоком. Исходная песня остаётся неизменной.')
        self.events = queue.Queue()
        self.busy = False
        self.closed = False
        self.pending = False
        self.revision = 0
        self.debounce = None
        self.last_image = None
        self.preview_photo = None
        self.classic_cache = None
        self.modern_cache = None
        self._layout()
        for variable in (self.engine, self.seed, self.size, self.detail, self.auto_detail,
                         self.mode, self.patterns, self.scheme, self.colors, self.contrast,
                         self.saturation, self.softness, self.composition, self.mood, self.title):
            variable.trace_add('write', self._changed)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(80, self._poll)
        self._update_enabled()

    def _layout(self):
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Музыка → изображение', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='M2Pv1 — классика · M2Pv2 — органика · M2Pv3 — органика и структура песни слева → направо',
                  style='Note.TLabel').pack(anchor='w', pady=(3, 12))
        file_row = ttk.Frame(outer)
        file_row.pack(fill='x', pady=(0, 12))
        ttk.Entry(file_row, textvariable=self.path, state='readonly').pack(side='left', fill='x', expand=True)
        ttk.Button(file_row, text='Выбрать песню…', command=self.choose_file).pack(side='left', padx=(8, 0))
        body = ttk.Frame(outer)
        body.pack(fill='both', expand=True)
        controls_view = ttk.Frame(body)
        controls_view.pack(side='left', fill='y', padx=(0, 16))
        self.controls_canvas = tk.Canvas(controls_view, width=440, height=540,
                                        background='#f4f4fa', highlightthickness=0)
        controls_scroll = ttk.Scrollbar(controls_view, orient='vertical', command=self.controls_canvas.yview)
        controls_scroll.pack(side='right', fill='y')
        self.controls_canvas.pack(side='left', fill='y', expand=True)
        self.controls_canvas.configure(yscrollcommand=controls_scroll.set)
        controls = ttk.Frame(self.controls_canvas)
        self.controls_canvas.create_window((0, 0), window=controls, anchor='nw', width=440)
        controls.bind('<Configure>', lambda event: self.controls_canvas.configure(scrollregion=self.controls_canvas.bbox('all')))
        self.root.bind('<MouseWheel>', lambda event: self.controls_canvas.yview_scroll(-int(event.delta / 120), 'units')
                       if str(event.widget).startswith(str(controls)) else None, add='+')
        preview = ttk.Frame(body)
        preview.pack(side='left', fill='both', expand=True)
        row = ttk.Frame(controls)
        row.pack(fill='x', pady=(0, 10))
        for value in ENGINES:
            ttk.Radiobutton(row, text=value, value=value, variable=self.engine).pack(side='left', padx=(0, 28))
        base = ttk.LabelFrame(controls, text='Вариант и детализация', padding=10)
        base.pack(fill='x', pady=(0, 10))
        first = ttk.Frame(base)
        first.pack(fill='x')
        ttk.Label(first, text='Seed').pack(side='left')
        ttk.Entry(first, textvariable=self.seed, width=12).pack(side='left', padx=8)
        ttk.Button(first, text='Другой вариант', command=self.random_seed).pack(side='left')
        ttk.Label(first, text='px').pack(side='right', padx=5)
        ttk.Combobox(first, textvariable=self.size, values=('512', '1000', '2048', '4096'), width=7).pack(side='right')
        ttk.Checkbutton(base, text='Автоматическая детализация по музыке', variable=self.auto_detail).pack(anchor='w', pady=(9, 0))
        self.detail_scale = self._slider(base, 'Детализация', self.detail, 0, 100)
        ttk.Label(base, text='Seed меняет вариант, а не сам характер песни.', style='Note.TLabel').pack(anchor='w')
        self.classic_box = ttk.LabelFrame(controls, text='M2Pv1: классический рисунок', padding=10)
        self.classic_box.pack(fill='x', pady=(0, 10))
        self.mode_control = self._combo(self.classic_box, 'Режим цвета', self.mode, ('ocean', 'plasma', 'fusion', 'aurora'))
        self.pattern_control = self._combo(self.classic_box, 'Узор: 1 проще, 2 богаче', self.patterns, ('1', '2'))
        self.modern_box = ttk.LabelFrame(controls, text='M2Pv2: современный рисунок', padding=10)
        self.modern_box.pack(fill='x', pady=(0, 10))
        self.composition_control = self._combo(self.modern_box, 'Композиция', self.composition, tuple(COMPOSITION_LABELS.values()))
        self.mood_control = self._combo(self.modern_box, 'Настроение', self.mood, tuple(MOOD_LABELS.values()))
        self.timeline_note = ttk.Label(self.modern_box,
            text='M2Pv3: слева начало, справа конец. Фон, цвет и плотность узора следуют изменениям песни.',
            wraplength=400, style='Note.TLabel')
        palette = ttk.LabelFrame(controls, text='Цветовая схема', padding=10)
        self.palette_box = palette
        palette.pack(fill='x', pady=(0, 10))
        self._combo(palette, 'Палитра', self.scheme, tuple(SCHEME_LABELS.values()))
        self.palette_strip = tk.Canvas(palette, height=22, width=380, highlightthickness=0)
        self.palette_strip.pack(fill='x', pady=5)
        self.colors_entry = ttk.Entry(palette, textvariable=self.colors)
        self.colors_entry.pack(fill='x')
        ttk.Button(palette, text='Добавить свой цвет…', command=self.add_color).pack(anchor='w', pady=(5, 0))
        ttk.Label(palette, text='Свои цвета: #RRGGBB через запятую, слева → направо.', style='Note.TLabel').pack(anchor='w')
        finish = ttk.LabelFrame(controls, text='Финишная обработка', padding=10)
        finish.pack(fill='x')
        self._slider(finish, 'Контраст, %', self.contrast, 50, 150)
        self._slider(finish, 'Насыщенность, %', self.saturation, 0, 150)
        self._slider(finish, 'Мягкость, %', self.softness, 0, 100)
        ttk.Checkbutton(finish, text='Название файла по центру', variable=self.title).pack(anchor='w')
        self.preview_canvas = tk.Canvas(preview, width=540, height=420, background='#e5e5ef', highlightthickness=0)
        self.preview_canvas.pack(fill='both', expand=True)
        self.preview_canvas.bind('<Configure>', lambda event: self._show_image())
        actions = ttk.Frame(preview)
        actions.pack(fill='x', pady=10)
        self.preview_button = ttk.Button(actions, text='Предпросмотр', command=self.preview)
        self.preview_button.pack(side='left')
        self.save_button = ttk.Button(actions, text='Сохранить PNG…', command=self.save, state='disabled')
        self.save_button.pack(side='left', padx=8)
        ttk.Button(actions, text='Сброс', command=self.reset).pack(side='right')
        ttk.Checkbutton(preview, text='Обновлять при изменении параметров', variable=self.automatic).pack(anchor='w')
        ttk.Label(preview, textvariable=self.analysis_text, wraplength=510, style='Note.TLabel').pack(fill='x', pady=10)
        self.progress = ttk.Progressbar(outer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(12, 4))
        ttk.Label(outer, textvariable=self.status, wraplength=1000, style='Note.TLabel').pack(anchor='w')

    def _combo(self, parent, label, variable, values):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=2)
        ttk.Label(row, text=label, width=23).pack(side='left')
        control = ttk.Combobox(row, textvariable=variable, values=values, state='readonly', width=27)
        control.pack(side='left', fill='x', expand=True)
        return control

    def _slider(self, parent, label, variable, lower, upper):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=3)
        ttk.Label(row, text=label, width=19).pack(side='left')
        control = ttk.Scale(row, variable=variable, from_=lower, to=upper)
        control.pack(side='left', fill='x', expand=True)
        value = ttk.Label(row, width=5, anchor='e')
        value.pack(side='left')
        variable.trace_add('write', lambda *_: value.configure(text=str(round(variable.get()))))
        value.configure(text=str(round(variable.get())))
        return control

    def _options(self):
        scheme = next(key for key, label in SCHEME_LABELS.items() if label == self.scheme.get())
        composition = next(key for key, label in COMPOSITION_LABELS.items() if label == self.composition.get())
        mood = next(key for key, label in MOOD_LABELS.items() if label == self.mood.get())
        return RenderOptions(engine=self.engine.get(), size=int(self.size.get()), seed=int(self.seed.get()),
                             detail=None if self.auto_detail.get() else self.detail.get(), color_mode=self.mode.get(),
                             patterns=int(self.patterns.get()), color_scheme=scheme, colors=parse_colors(self.colors.get()),
                             contrast=self.contrast.get(), saturation=self.saturation.get(), softness=self.softness.get(),
                             composition=composition, mood=mood, center_title=self.title.get()).validated()

    def _changed(self, *_):
        self.revision += 1
        self._update_enabled()
        if self.debounce:
            self.root.after_cancel(self.debounce)
        if self.path.get() and self.automatic.get():
            self.debounce = self.root.after(400, self.preview)

    def _update_enabled(self):
        classic = self.engine.get() == 'M2Pv1'
        timeline = self.engine.get() == 'M2Pv3'
        self.modern_box.configure(text='M2Pv3: узор и структура песни' if timeline else 'M2Pv2: современный рисунок')
        self.timeline_note.pack_forget()
        if timeline:
            self.timeline_note.pack(anchor='w', pady=(6, 0))
        self.classic_box.pack_forget()
        self.modern_box.pack_forget()
        (self.classic_box if classic else self.modern_box).pack(fill='x', pady=(0, 10), before=self.palette_box)
        for control in (self.mode_control, self.pattern_control):
            control.configure(state='readonly' if classic else 'disabled')
        for control in (self.composition_control, self.mood_control):
            control.configure(state='disabled' if classic else 'readonly')
        self.detail_scale.configure(state='disabled' if self.auto_detail.get() else 'normal')
        self.colors_entry.configure(state='normal' if self.scheme.get() == SCHEME_LABELS['custom'] else 'disabled')
        self.palette_strip.delete('all')
        key = next(key for key, label in SCHEME_LABELS.items() if label == self.scheme.get())
        colors = parse_colors(self.colors.get()) if key == 'custom' else COLOR_SCHEMES[key]
        colors = colors or ('#6551C7', '#8496BF', '#C697BD', '#EF917D', '#F8CF8C')
        width = max(380, self.palette_strip.winfo_width())
        for index, color in enumerate(colors):
            try:
                self.palette_strip.create_rectangle(index * width / len(colors), 0,
                    (index + 1) * width / len(colors) + 1, 22, fill=color, outline='')
            except tk.TclError:
                pass

    def choose_file(self):
        selected = filedialog.askopenfilename(title='Выберите музыку', filetypes=[
            ('Музыка', '*.mp3 *.flac *.wav *.m4a *.aac *.ogg *.opus *.wma'), ('Все файлы', '*.*')])
        if selected:
            self.path.set(selected)
            self.revision += 1
            self.preview()

    def random_seed(self):
        self.seed.set(str(random.randrange(2**31)))
        if not self.automatic.get():
            self.preview()

    def add_color(self):
        color = colorchooser.askcolor(title='Добавить цвет')[1]
        if color:
            key = next(key for key, label in SCHEME_LABELS.items() if label == self.scheme.get())
            colors = parse_colors(self.colors.get()) if key == 'custom' else COLOR_SCHEMES[key]
            self.colors.set(', '.join((*colors, color)))
            self.scheme.set(SCHEME_LABELS['custom'])

    def reset(self):
        for variable, value in ((self.seed, '0'), (self.size, '1000'), (self.detail, 50),
            (self.auto_detail, True), (self.mode, 'plasma'), (self.patterns, '2'),
            (self.colors, '#25143B, #64365E, #AE4663, #EE6A53, #FFC078'),
            (self.scheme, SCHEME_LABELS['auto']), (self.contrast, 100), (self.saturation, 100),
            (self.softness, 0), (self.composition, COMPOSITION_LABELS['auto']),
            (self.mood, MOOD_LABELS['auto']), (self.title, False)):
            variable.set(value)

    def preview(self):
        if self.debounce:
            self.root.after_cancel(self.debounce)
        self.debounce = None
        if self.busy:
            self.pending = True
            return
        self._start('preview')

    def save(self):
        if self.busy:
            return
        target = filedialog.asksaveasfilename(title='Сохранить обложку', defaultextension='.png',
                                            initialfile=Path(self.path.get()).stem + '_cover.png', filetypes=[('PNG', '*.png')])
        if target:
            self._start('save', target)

    def _start(self, kind, target=None):
        try:
            options = self._options()
            source = Path(self.path.get()).resolve()
            if not source.is_file() or source.suffix.lower() not in AUDIO_TYPES:
                raise ValueError('Выберите существующий локальный аудиофайл поддерживаемого формата.')
            if target and Path(target).resolve() == source:
                raise ValueError('PNG нельзя сохранить поверх исходной песни.')
            if not shutil.which('ffmpeg'):
                raise ValueError('Нужен FFmpeg: добавьте его bin в PATH либо положите ffmpeg.exe в папку tools рядом с M2P-Studio.exe. Инструкция есть в README.')
        except (ValueError, OSError) as exc:
            self.status.set(str(exc))
            return
        self.busy = True
        self.pending = False
        self.preview_button.configure(state='disabled')
        self.save_button.configure(state='disabled')
        self.progress.start(12)
        self.status.set('Чтение и анализ песни… При следующих изменениях неизменённая песня не декодируется заново.')
        threading.Thread(target=self._work, args=(kind, source, options, target, self.revision), daemon=True).start()

    def _work(self, kind, source, options, target, revision):
        try:
            stat = source.stat()
            key = (str(source), stat.st_size, stat.st_mtime_ns)
            bundle = classic = None
            summary = 'M2Pv1: спектр, громкость, бас, атаки и энергия → исходные поля и контуры.'
            if options.engine == 'M2Pv1':
                from music2picture_v1 import analyze_track
                if self.classic_cache is None or self.classic_cache[0] != key:
                    self.classic_cache = (key, analyze_track(source))
                classic = self.classic_cache[1]
                if self.modern_cache is not None and self.modern_cache[0][:3] != key:
                    self.modern_cache = None
            else:
                from music2picture_v2 import DEFAULT_PIPELINE
                modern_key = (*key, options.mood)
                if self.modern_cache is None or self.modern_cache[0] != modern_key:
                    self.modern_cache = (modern_key, DEFAULT_PIPELINE.analyse(
                        source, metadata={'title': source.stem}, mood_override=options.mood,
                        progress=lambda stage: self.events.put(('stage', stage.replace('_', ' ')))))
                bundle = self.modern_cache[1]
                if self.classic_cache is not None and self.classic_cache[0] != key:
                    self.classic_cache = None
                summary = bundle.song_description
                if options.engine == 'M2Pv3':
                    summary = 'M2Pv3: начало слева → конец справа; фон показывает спектр, активность и переходы песни. ' + summary
            self.events.put(('stage', 'Создание рисунка…'))
            render_options = options if kind == 'save' else replace(options, size=min(options.size, 1000))
            image = render_with_options(source, render_options, bundle=bundle, classic_analysis=classic)
            if options.center_title:
                from music2picture import _draw_optional_title
                _draw_optional_title(image, source.stem)
            if kind == 'save':
                image.save(target, 'PNG', optimize=True)
                from music2picture import _save_profile
                _save_profile(Path(target), source, bundle, options.seed, options.center_title, options=options)
            self.events.put(('done', kind, image, target, revision, summary))
        except Exception as exc:
            self.events.put(('error', str(exc)))

    def _poll(self):
        if self.closed:
            return
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'stage':
                    self.status.set(event[1])
                    continue
                self.busy = False
                self.progress.stop()
                self.preview_button.configure(state='normal')
                if event[0] == 'done':
                    _, kind, image, target, revision, summary = event
                    if revision == self.revision:
                        self.last_image = image
                        self._show_image()
                        self.analysis_text.set(summary)
                    self.status.set(f'Сохранено: {target}' if kind == 'save' else 'Готово. Меняйте параметры или сохраните полный PNG.')
                else:
                    self.status.set('Ошибка: ' + event[1])
                self.save_button.configure(state='normal' if self.last_image is not None else 'disabled')
                if self.pending:
                    self.pending = False
                    self.root.after_idle(self.preview)
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _show_image(self):
        if self.last_image is None:
            return
        width, height = self.preview_canvas.winfo_width(), self.preview_canvas.winfo_height()
        size = max(64, min(width, height) - 20)
        image = self.last_image.resize((size, size), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(image, master=self.root)
        self.preview_canvas.delete('all')
        self.preview_canvas.create_image(width // 2, height // 2, image=self.preview_photo)

    def close(self):
        self.closed = True
        self.root.destroy()


def main():
    configure_tools()
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from m2p_selftest import run
        raise SystemExit(0 if run(sys.argv[2]) else 1)
    root = tk.Tk()
    Playground(root)
    root.mainloop()


if __name__ == '__main__':
    main()
