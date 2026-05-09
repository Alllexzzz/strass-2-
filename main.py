import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
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

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Генератор схем для страз v1.0")
        self.geometry("900x800")  # увеличил окно
        self.image_path = None
        self.processed_image = None
        self.setup_ui()
        
    def setup_ui(self):
        # Заголовок
        tk.Label(self, text="🎨 Генератор схем для выкладки картин бисером", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Кнопка загрузки
        tk.Button(self, text="📁 Загрузить фото", command=self.load_image, bg="#4CAF50", fg="white", font=("Arial", 12)).pack(pady=5)
        
        # Превью (увеличено)
        self.preview_label = tk.Label(self, text="Фото не выбрано", bg="lightgray", width=100, height=20)
        self.preview_label.pack(pady=10)
        
        # Панель настроек
        settings_frame = tk.Frame(self)
        settings_frame.pack(pady=10)
        
        tk.Label(settings_frame, text="Размер страз:", font=("Arial", 11)).grid(row=0, column=0, padx=5)
        self.size_var = tk.StringVar(value="SS16 (4.0 мм)")
        size_menu = ttk.Combobox(settings_frame, textvariable=self.size_var, values=list(STRASS_SIZES.keys()), width=15)
        size_menu.grid(row=0, column=1, padx=5)
        
        tk.Label(settings_frame, text="Ширина (см):", font=("Arial", 11)).grid(row=0, column=2, padx=5)
        self.width_var = tk.DoubleVar(value=40.0)
        tk.Spinbox(settings_frame, textvariable=self.width_var, from_=5.0, to=150.0, increment=1.0, width=10).grid(row=0, column=3, padx=5)
        
        tk.Label(settings_frame, text="Цветов:", font=("Arial", 11)).grid(row=0, column=4, padx=5)
        self.colors_var = tk.IntVar(value=25)
        tk.Spinbox(settings_frame, textvariable=self.colors_var, from_=5, to=50, width=8).grid(row=0, column=5, padx=5)
        
        self.bg_var = tk.BooleanVar(value=False)
        tk.Checkbutton(settings_frame, text="Вырезать объект с фона", variable=self.bg_var).grid(row=1, column=0, columnspan=6, pady=5)
        
        # Кнопки действий
        tk.Button(self, text="⚙️ Сгенерировать схему", command=self.start_processing, bg="#2196F3", fg="white", font=("Arial", 12)).pack(pady=5)
        self.status_label = tk.Label(self, text="Готов к работе", font=("Arial", 10))
        self.status_label.pack(pady=10)
        
    def load_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")])
        if path:
            self.image_path = path
            img = Image.open(path)
            # Увеличил превью до 700x500
            img.thumbnail((700, 500))
            photo = ImageTk.PhotoImage(img)
            self.preview_label.config(image=photo, text="")
            self.preview_label.image = photo
            self.status_label.config(text=f"Загружено: {os.path.basename(path)}")
            
    def start_processing(self):
        if not self.image_path:
            messagebox.showerror("Ошибка", "Сначала загрузите фото!")
            return
        self.status_label.config(text="Идёт обработка...")
        threading.Thread(target=self.generate_schema, daemon=True).start()
        
    def generate_schema(self):
        try:
            # Загрузка и предобработка
            img = Image.open(self.image_path).convert("RGB")
            if self.bg_var.get():
                img = remove(img.convert("RGBA")).convert("RGB")
            
            img_array = np.array(img)
            bead_size_mm = STRASS_SIZES[self.size_var.get()]
            desired_width_cm = self.width_var.get()
            num_colors = self.colors_var.get()
            
            # Анализ сложности
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            
            # Уменьшение цветов
            img_pil = Image.fromarray(img_array)
            quantized = img_pil.quantize(colors=num_colors, method=Image.Quantize.MEDIANCUT).convert("RGB")
            
            # Создание PDF
            pdf = FPDF(orientation='L', unit='mm', format='A3')
            pdf.add_page()
            
            beads_per_cm = 10 / bead_size_mm
            target_width = int(desired_width_cm * beads_per_cm)
            w_percent = target_width / img_array.shape[1]
            target_height = int(img_array.shape[0] * w_percent)
            
            block_size = max(8, min(img_array.shape[0], img_array.shape[1]) // 60)
            cell_size = min(380 / target_width, 250 / target_height)
            
            for y in range(target_height):
                for x in range(target_width):
                    # Определяем оригинальные координаты
                    orig_y = int(y / target_height * img_array.shape[0])
                    orig_x = int(x / target_width * img_array.shape[1])
                    
                    # Блок для сложности
                    block_y = min(orig_y // block_size, (img_array.shape[0] // block_size) - 1)
                    block_x = min(orig_x // block_size, (img_array.shape[1] // block_size) - 1)
                    
                    block = edges[block_y*block_size:(block_y+1)*block_size,
                                 block_x*block_size:(block_x+1)*block_size]
                    complexity = np.count_nonzero(block) / (block_size * block_size)
                    
                    # Радиус кружка
                    base_radius = cell_size / 2 - 0.1
                    if complexity > 0.3:
                        radius = base_radius * 0.6
                    elif complexity > 0.1:
                        radius = base_radius * 0.8
                    else:
                        radius = base_radius
                    
                    # Цвет
                    r, g, b = quantized.getpixel((orig_x, orig_y))
                    pdf.set_fill_color(r, g, b)
                    
                    cx = x * cell_size + 10 + cell_size/2
                    cy = y * cell_size + 10 + cell_size/2
                    # ИСПРАВЛЕНО: используем ellipse вместо circle
                    pdf.ellipse(cx - radius, cy - radius, 2*radius, 2*radius, 'F')
            
            # Сохранение
            save_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
            if save_path:
                pdf.output(save_path)
                self.status_label.config(text=f"Схема сохранена: {os.path.basename(save_path)}")
                messagebox.showinfo("Успех", "Схема успешно создана!")
            else:
                self.status_label.config(text="Сохранение отменено")
        except Exception as e:
            self.status_label.config(text="Ошибка при обработке!")
            messagebox.showerror("Ошибка", str(e))

if __name__ == "__main__":
    app = Application()
    app.mainloop()
