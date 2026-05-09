import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageDraw
import numpy as np
import cv2
from fpdf import FPDF
import os
from rembg import remove
import threading

# Таблица размеров страз
STRASS_SIZES = {
    "SS6 (2.0 мм)": 2.0,
    "SS10 (2.8 мм)": 2.8,
    "SS12 (3.1 мм)": 3.1,
    "SS16 (4.0 мм)": 4.0,
    "SS20 (4.8 мм)": 4.8,
    "SS30 (6.4 мм)": 6.4,
    "SS34 (7.4 мм)": 7.4,
    "SS40 (8.5 мм)": 8.5
}

def get_closest_strass(diameter_mm, sizes_dict):
    """Возвращает ключ (название SS) и значение (диаметр) ближайшего размера"""
    best = None
    best_dist = float('inf')
    for name, size in sizes_dict.items():
        dist = abs(size - diameter_mm)
        if dist < best_dist:
            best_dist = dist
            best = (name, size)
    return best

def auto_recommend_size(complexity_map, edges, default_mm=4.0):
    """Анализирует сложность изображения и рекомендует базовый размер страза"""
    total_blocks = complexity_map.size
    hard_blocks = np.count_nonzero(complexity_map > 0.3)
    hard_ratio = hard_blocks / max(total_blocks, 1)
    if hard_ratio > 0.4:
        suggested_mm = 2.0  # SS6
    elif hard_ratio > 0.2:
        suggested_mm = 2.8  # SS10
    elif hard_ratio > 0.1:
        suggested_mm = 3.1  # SS12
    else:
        suggested_mm = 4.0  # SS16
    return get_closest_strass(suggested_mm, STRASS_SIZES)

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Генератор схем для страз v4.0")
        self.geometry("1100x850")
        self.image_path = None
        self.original_image = None
        self.schema_preview = None
        self.pdf = None
        self.setup_ui()

    def setup_ui(self):
        # Панель инструментов
        toolbar = tk.Frame(self, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        tk.Button(toolbar, text="📁 Загрузить фото", command=self.load_image, bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="⚙️ Сгенерировать схему", command=self.start_processing, bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="🖼️ Предпросмотр схемы", command=self.show_schema_preview, bg="#FF9800", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="💾 Сохранить PDF", command=self.save_pdf, bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="🖼️ Сохранить PNG", command=lambda: self.save_schema_image("png"), bg="#9C27B0", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="🖼️ Сохранить JPEG", command=lambda: self.save_schema_image("jpeg"), bg="#9C27B0", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="Выход", command=self.quit, bg="#f44336", fg="white").pack(side=tk.RIGHT, padx=2, pady=2)

        # Основная область
        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Левая панель: превью загруженного изображения
        left_frame = tk.LabelFrame(main_frame, text="Исходное изображение", padx=5, pady=5)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(left_frame, width=800, height=600, bg="lightgray")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Правая панель: настройки
        right_frame = tk.LabelFrame(main_frame, text="Параметры", padx=5, pady=5)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5,0))

        tk.Label(right_frame, text="Размер страз:").pack(anchor=tk.W)
        self.size_var = tk.StringVar(value="SS16 (4.0 мм)")
        self.size_combo = ttk.Combobox(right_frame, textvariable=self.size_var, values=list(STRASS_SIZES.keys()), width=18)
        self.size_combo.pack(anchor=tk.W, pady=2)

        tk.Button(right_frame, text="Автоопределить размер", command=self.auto_size).pack(anchor=tk.W, pady=2)

        tk.Label(right_frame, text="Ширина картины (см):").pack(anchor=tk.W)
        self.width_var = tk.DoubleVar(value=40.0)
        tk.Spinbox(right_frame, textvariable=self.width_var, from_=5.0, to=150.0, increment=1.0, width=10).pack(anchor=tk.W, pady=2)

        tk.Label(right_frame, text="Детализация (страз в ширину):").pack(anchor=tk.W)
        self.detail_var = tk.IntVar(value=400)
        tk.Scale(right_frame, from_=100, to=800, orient=tk.HORIZONTAL, variable=self.detail_var).pack(anchor=tk.W, pady=2)

        tk.Label(right_frame, text="Количество цветов:").pack(anchor=tk.W)
        self.colors_var = tk.IntVar(value=25)
        tk.Spinbox(right_frame, textvariable=self.colors_var, from_=5, to=50, width=10).pack(anchor=tk.W, pady=2)

        self.bg_var = tk.BooleanVar(value=False)
        tk.Checkbutton(right_frame, text="Вырезать объект с фона", variable=self.bg_var).pack(anchor=tk.W, pady=5)

        # Статус и прогресс
        self.status_label = tk.Label(self, text="Готов к работе", font=("Arial", 10))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(self, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(0,5))

    def load_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")])
        if not path:
            return
        self.image_path = path
        self.original_image = Image.open(path).convert("RGB")
        self.display_on_canvas(self.original_image)
        self.status_label.config(text=f"Загружено: {os.path.basename(path)}")

    def display_on_canvas(self, img):
        w, h = img.size
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            canvas_w, canvas_h = 800, 600
        ratio = min(canvas_w / w, canvas_h / h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        display_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(display_img)
        self.canvas.delete("all")
        self.canvas.create_image(canvas_w//2, canvas_h//2, image=self.tk_image, anchor=tk.CENTER)

    def auto_size(self):
        if self.original_image is None:
            messagebox.showwarning("Нет изображения", "Сначала загрузите фото.")
            return
        img_array = np.array(self.original_image)
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        block_size = max(8, min(img_array.shape[0], img_array.shape[1]) // 60)
        h_blocks = img_array.shape[0] // block_size
        w_blocks = img_array.shape[1] // block_size
        complexity_map = np.zeros((h_blocks, w_blocks))
        for i in range(h_blocks):
            for j in range(w_blocks):
                block = edges[i*block_size:(i+1)*block_size, j*block_size:(j+1)*block_size]
                complexity_map[i, j] = np.count_nonzero(block) / (block_size * block_size)
        ss_name, _ = auto_recommend_size(complexity_map, edges)
        self.size_var.set(ss_name)
        self.status_label.config(text=f"Рекомендован размер: {ss_name}")

    def start_processing(self):
        if self.original_image is None:
            messagebox.showerror("Ошибка", "Сначала загрузите фото!")
            return
        self.progress_var.set(0)
        self.status_label.config(text="Идёт обработка...")
        threading.Thread(target=self.generate_schema, daemon=True).start()

    def generate_schema(self):
        try:
            img = self.original_image.copy()
            if self.bg_var.get():
                self.update_status("Удаление фона...", 5)
                img = remove(img.convert("RGBA")).convert("RGB")

            img_array = np.array(img)
            bead_size_mm = STRASS_SIZES[self.size_var.get()]
            desired_width_cm = self.width_var.get()
            num_colors = self.colors_var.get()
            target_width = self.detail_var.get()  # основное разрешение

            # Вычисляем высоту, сохраняя пропорции
            ratio = img_array.shape[0] / img_array.shape[1]
            target_height = int(target_width * ratio)

            self.update_status("Уменьшение цветов...", 10)
            img_pil = Image.fromarray(img_array)
            quantized = img_pil.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT).convert("RGB")

            self.update_status("Построение схемы...", 20)
            # Создаём превью (полноразмерное)
            preview_img = Image.new("RGB", (target_width, target_height), "white")
            draw_preview = ImageDraw.Draw(preview_img)

            # PDF-документ
            pdf = FPDF(orientation='L', unit='mm', format='A3')
            pdf.add_page()
            # Вычисляем размер ячейки, чтобы вписать в A3 (420x297 мм с полями)
            cell_size = min(380 / target_width, 250 / target_height)
            radius = cell_size * 0.45  # чтобы круги не слипались

            stats = {}
            total = target_height

            for y in range(target_height):
                if y % 10 == 0:
                    percent = 20 + (y / total) * 60
                    self.update_progress(percent)
                for x in range(target_width):
                    # Определяем исходные координаты пикселя
                    orig_x = int(x / target_width * img_array.shape[1])
                    orig_y = int(y / target_height * img_array.shape[0])

                    # Берём цвет из квантованного изображения
                    r, g, b = quantized.getpixel((orig_x, orig_y))

                    # Используем один размер страза для всех кружков (без адаптивности)
                    ss_name = self.size_var.get()

                    # Рисуем в PDF
                    pdf.set_fill_color(r, g, b)
                    cx = x * cell_size + 10 + cell_size/2
                    cy = y * cell_size + 10 + cell_size/2
                    pdf.ellipse(cx - radius, cy - radius, 2*radius, 2*radius, 'F')

                    # Статистика
                    key = (r, g, b, ss_name)
                    stats[key] = stats.get(key, 0) + 1

                    # Рисуем в превью (один кружок = один пиксель для простоты, т.к. их много, будет мелко, но на весь рисунок)
                    draw_preview.point((x, y), fill=(r, g, b))

            self.update_status("Формирование легенды...", 85)
            # Легенда в PDF
            pdf.add_page()
            pdf.set_font("Arial", size=8)
            pdf.text(10, 10, "Легенда схемы (цвет, размер страз, количество)")

            y_cursor = 18
            grouped = {}
            for (r, g, b, ss), count in sorted(stats.items(), key=lambda x: (x[0][2], x[0][1], x[0][0])):
                grouped.setdefault((r,g,b), []).append((ss, count))

            for (r,g,b), items in grouped.items():
                pdf.set_fill_color(r, g, b)
                pdf.rect(10, y_cursor, 4, 4, 'F')
                pdf.set_text_color(0, 0, 0)
                ss_list = ", ".join([f"{ss}: {cnt} шт." for ss, cnt in items])
                pdf.text(16, y_cursor + 3, f"RGB({r},{g},{b})   {ss_list}")
                y_cursor += 6
                if y_cursor > 190:
                    pdf.add_page()
                    y_cursor = 10

            self.pdf = pdf
            self.schema_preview = preview_img
            self.update_status("Готово!", 100)
            self.progress_var.set(100)
            messagebox.showinfo("Успех", "Схема создана! Можно сохранить PDF или изображение.")

        except Exception as e:
            self.update_status(f"Ошибка: {e}", 0)
            messagebox.showerror("Ошибка", str(e))

    def update_status(self, text, percent):
        self.status_label.config(text=text)
        self.progress_var.set(percent)
        self.update_idletasks()

    def update_progress(self, percent):
        self.progress_var.set(percent)
        self.update_idletasks()

    def save_pdf(self):
        if self.pdf is None:
            messagebox.showinfo("Сохранение", "Сначала сгенерируйте схему.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".pdf",
                                            filetypes=[("PDF files", "*.pdf")])
        if path:
            try:
                self.pdf.output(path)
                self.status_label.config(text=f"PDF сохранён: {os.path.basename(path)}")
                messagebox.showinfo("Сохранение", f"Файл {path} сохранён.")
            except Exception as e:
                messagebox.showerror("Ошибка сохранения", str(e))

    def show_schema_preview(self):
        if self.schema_preview is None:
            messagebox.showinfo("Предпросмотр", "Сначала сгенерируйте схему.")
            return
        preview_win = tk.Toplevel(self)
        preview_win.title("Предпросмотр схемы")
        w, h = self.schema_preview.size
        # Вписываем в окно 900x700
        max_w, max_h = 900, 700
        ratio = min(max_w/w, max_h/h, 1.0)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        show_img = self.schema_preview.resize((new_w, new_h), Image.Resampling.NEAREST)
        photo = ImageTk.PhotoImage(show_img)
        canvas = tk.Canvas(preview_win, width=new_w, height=new_h)
        canvas.pack()
        canvas.create_image(0,0, image=photo, anchor=tk.NW)
        canvas.image = photo
        tk.Button(preview_win, text="Закрыть", command=preview_win.destroy).pack(pady=5)

    def save_schema_image(self, fmt):
        if self.schema_preview is None:
            messagebox.showinfo("Сохранение", "Сначала сгенерируйте схему.")
            return
        path = filedialog.asksaveasfilename(defaultextension=f".{fmt}",
                                            filetypes=[(f"{fmt.upper()} files", f"*.{fmt}")])
        if path:
            try:
                self.schema_preview.save(path)
                self.status_label.config(text=f"Изображение сохранено: {os.path.basename(path)}")
                messagebox.showinfo("Сохранение", f"Файл {path} сохранён.")
            except Exception as e:
                messagebox.showerror("Ошибка", str(e))

if __name__ == "__main__":
    app = Application()
    app.mainloop()
