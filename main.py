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
    best = None
    best_dist = float('inf')
    for name, size in sizes_dict.items():
        dist = abs(size - diameter_mm)
        if dist < best_dist:
            best_dist = dist
            best = (name, size)
    return best

def auto_recommend_size(complexity_map, edges, default_mm=4.0):
    total_blocks = complexity_map.size
    hard_blocks = np.count_nonzero(complexity_map > 0.3)
    hard_ratio = hard_blocks / max(total_blocks, 1)
    if hard_ratio > 0.4:
        suggested_mm = 2.0
    elif hard_ratio > 0.2:
        suggested_mm = 2.8
    elif hard_ratio > 0.1:
        suggested_mm = 3.1
    else:
        suggested_mm = 4.0
    return get_closest_strass(suggested_mm, STRASS_SIZES)

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Генератор схем для страз v3.1")
        self.geometry("1100x850")
        self.image_path = None
        self.original_image = None
        self.schema_preview = None
        self.pdf = None
        self.setup_ui()

    def setup_ui(self):
        toolbar = tk.Frame(self, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        tk.Button(toolbar, text="📁 Загрузить фото", command=self.load_image, bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="⚙️ Сгенерировать схему", command=self.start_processing, bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="🖼️ Предпросмотр схемы", command=self.show_schema_preview, bg="#FF9800", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="💾 Сохранить PDF", command=self.save_pdf, bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="🖼️ Сохранить PNG", command=lambda: self.save_schema_image("png"), bg="#9C27B0", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="🖼️ Сохранить JPEG", command=lambda: self.save_schema_image("jpeg"), bg="#9C27B0", fg="white").pack(side=tk.LEFT, padx=2, pady=2)
        tk.Button(toolbar, text="Выход", command=self.quit, bg="#f44336", fg="white").pack(side=tk.RIGHT, padx=2, pady=2)

        main_frame = tk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        left_frame = tk.LabelFrame(main_frame, text="Исходное изображение", padx=5, pady=5)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(left_frame, width=800, height=600, bg="lightgray")
        self.canvas.pack(fill=tk.BOTH, expand=True)

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

        tk.Label(right_frame, text="Количество цветов:").pack(anchor=tk.W)
        self.colors_var = tk.IntVar(value=25)
        tk.Spinbox(right_frame, textvariable=self.colors_var, from_=5, to=50, width=10).pack(anchor=tk.W, pady=2)

        self.bg_var = tk.BooleanVar(value=False)
        tk.Checkbutton(right_frame, text="Вырезать объект с фона", variable=self.bg_var).pack(anchor=tk.W, pady=5)

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

            self.update_status("Анализ сложности...", 10)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 50, 150)

            self.update_status("Уменьшение цветов...", 20)
            img_pil = Image.fromarray(img_array)
            quantized = img_pil.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT).convert("RGB")

            beads_per_cm = 10 / bead_size_mm
            target_width = int(desired_width_cm * beads_per_cm)
            w_percent = target_width / img_array.shape[1]
            target_height = int(img_array.shape[0] * w_percent)

            block_size = max(8, min(img_array.shape[0], img_array.shape[1]) // 60)
            cell_size = min(380 / target_width, 250 / target_height)
            base_radius = cell_size / 2 - 0.1

            # Создаем превью в полном размере (1:1)
            self.update_status("Построение схемы...", 30)
            preview_img = Image.new("RGB", (target_width, target_height), "white")
            draw_preview = ImageDraw.Draw(preview_img)

            pdf = FPDF(orientation='L', unit='mm', format='A3')
            pdf.add_page()

            stats = {}
            total_pixels = target_height

            for y in range(target_height):
                percent = 30 + (y / total_pixels) * 50
                if y % 10 == 0:
                    self.update_progress(percent)
                for x in range(target_width):
                    orig_y = int(y / target_height * img_array.shape[0])
                    orig_x = int(x / target_width * img_array.shape[1])

                    block_y = min(orig_y // block_size, (img_array.shape[0] // block_size) - 1)
                    block_x = min(orig_x // block_size, (img_array.shape[1] // block_size) - 1)
                    block = edges[block_y*block_size:(block_y+1)*block_size,
                                 block_x*block_size:(block_x+1)*block_size]
                    complexity = np.count_nonzero(block) / (block_size * block_size)

                    if complexity > 0.3:
                        radius = base_radius * 0.6
                    elif complexity > 0.1:
                        radius = base_radius * 0.8
                    else:
                        radius = base_radius

                    actual_diameter = bead_size_mm * (radius / base_radius)
                    ss_name, _ = get_closest_strass(actual_diameter, STRASS_SIZES)

                    r, g, b = quantized.getpixel((orig_x, orig_y))

                    # PDF
                    pdf.set_fill_color(r, g, b)
                    cx = x * cell_size + 10 + cell_size/2
                    cy = y * cell_size + 10 + cell_size/2
                    pdf.ellipse(cx - radius, cy - radius, 2*radius, 2*radius, 'F')

                    # Статистика
                    key = (r, g, b, ss_name)
                    stats[key] = stats.get(key, 0) + 1

                    # Полноразмерный предпросмотр (один кружок — один пиксель или больше?)
                    # Рисуем кружок диаметром 2 пикселя для наглядности
                    draw_preview.ellipse([x-1, y-1, x+1, y+1], fill=(r,g,b))

            self.update_status("Формирование легенды...", 85)
            pdf.add_page()
            pdf.set_font("Arial", size=8)
            pdf.text(10, 10, "Легенда схемы (цвет, размер стразы, количество штук)")

            y_cursor = 18
            grouped = {}
            for (r, g, b, ss), count in sorted(stats.items(), key=lambda x: (x[0][0], x[0][1], x[0][2], x[0][3])):
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
            messagebox.showinfo("Успех", "Схема создана. Вы можете сохранить PDF или изображение.")

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
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if path:
            self.pdf.output(path)
            self.status_label.config(text=f"PDF сохранён: {os.path.basename(path)}")
            messagebox.showinfo("Сохранение", f"Файл {path} сохранён.")

    def show_schema_preview(self):
        if self.schema_preview is None:
            messagebox.showinfo("Предпросмотр", "Сначала сгенерируйте схему.")
            return
        preview_win = tk.Toplevel(self)
        preview_win.title("Предпросмотр схемы")
        w, h = self.schema_preview.size
        # Ограничим максимальный размер окна 900x700 и впишем изображение
        max_w, max_h = 900, 700
        ratio = min(max_w/w, max_h/h, 1.0)  # не увеличиваем, если меньше
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
            self.schema_preview.save(path)
            self.status_label.config(text=f"Изображение сохранено: {os.path.basename(path)}")
            messagebox.showinfo("Сохранение", f"Файл {path} сохранён.")

if __name__ == "__main__":
    app = Application()
    app.mainloop()
