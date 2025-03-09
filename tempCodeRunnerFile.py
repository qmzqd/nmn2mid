import os
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tempfile
from nmn2midi_core import parse_input, create_midi

class NMNConverterApp:
    def __init__(self, root):
        self.root = root
        root.title("NMN2MIDI Converter v1.2")
        root.geometry("1100x750")
        self.default_output_dir = os.path.join(os.getcwd(), "outputs")
        self.setup_ui()
        self.setup_bindings()
        
    def setup_ui(self):
        style = ttk.Style()
        style.configure("TLabel", font=('Consolas', 10))
        style.configure("TButton", font=('Consolas', 10))
        style.configure("Status.TLabel", font=('Consolas', 9), foreground="#666")
        
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        self.create_file_controls(main_frame)
        self.create_settings_panel(main_frame)
        self.create_editor(main_frame)
        
        self.status_bar = ttk.Label(self.root, style="Status.TLabel", anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=5)
        
        self.tip_label = ttk.Label(
            self.root,
            text="💡 提示：拖放文件导入 | Ctrl+S 快速生成 | Alt+↑/↓ 跳转行号",
            style="Status.TLabel"
        )
        self.tip_label.pack(side=tk.BOTTOM, fill=tk.X, padx=15)
        
    def create_file_controls(self, parent):
        frame = ttk.LabelFrame(parent, text="文件操作", padding=10)
        frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=5)
        
        ttk.Label(frame, text="输入文件:").grid(row=0, column=0, sticky="w")
        self.input_path = ttk.Entry(frame, width=60)
        self.input_path.grid(row=0, column=1, padx=5, sticky="ew")
        ttk.Button(frame, text="浏览", command=self.browse_input, width=8).grid(row=0, column=2)
        
        ttk.Label(frame, text="输出文件:").grid(row=1, column=0, sticky="w")
        self.output_path = ttk.Entry(frame, width=60)
        self.output_path.grid(row=1, column=1, padx=5, sticky="ew")
        ttk.Button(frame, text="浏览", command=self.browse_output, width=8).grid(row=1, column=2)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=10)
        ttk.Button(btn_frame, text="🎵 生成MIDI", command=self.generate, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🧹 清空", command=self.clear_editor, width=8).pack(side=tk.LEFT)
        
        frame.columnconfigure(1, weight=1)
        
    def create_settings_panel(self, parent):
        frame = ttk.LabelFrame(parent, text="全局参数", padding=10)
        frame.grid(row=1, column=0, sticky="nsew", pady=5)
        
        ttk.Label(frame, text="速度 (BPM):").grid(row=0, column=0, sticky="w")
        self.tempo = ttk.Spinbox(frame, from_=20, to=300, width=5)
        self.tempo.set(120)
        self.tempo.grid(row=0, column=1, padx=5)
        
        ttk.Label(frame, text="拍号:").grid(row=0, column=2, sticky="w", padx=10)
        self.time_num = ttk.Combobox(frame, values=["2","3","4","5","6","7"], width=3)
        self.time_num.set("4")
        self.time_num.grid(row=0, column=3)
        ttk.Label(frame, text="/").grid(row=0, column=4)
        self.time_den = ttk.Combobox(frame, values=["2","4","8","16"], width=3)
        self.time_den.set("4")
        self.time_den.grid(row=0, column=5)
        
        ttk.Label(frame, text="调号:").grid(row=0, column=6, sticky="w", padx=10)
        self.key = ttk.Combobox(frame, values=[
            "C", "C#", "D", "D#", "E", "F", 
            "F#", "G", "G#", "A", "A#", "B"
        ], width=3)
        self.key.set("C")
        self.key.grid(row=0, column=7)
        
    def create_editor(self, parent):
        frame = ttk.LabelFrame(parent, text="乐谱编辑器", padding=10)
        frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=5)
        
        # 使用相同字体保证行高一致
        self.line_numbers = tk.Text(
            frame, 
            width=4,
            padx=4,
            takefocus=0,
            border=0,
            background="#f0f0f0",
            state="disabled",
            font=('Consolas', 12),
            wrap=tk.NONE
        )
        
        self.editor = tk.Text(
            frame,
            wrap=tk.NONE,
            font=('Consolas', 12),
            undo=True,
            padx=10,
            pady=10
        )
        
        # 滚动条配置
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.dual_scroll)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.editor.xview)
        
        self.editor.configure(
            yscrollcommand=lambda *args: self.on_text_scroll(*args, vsb),
            xscrollcommand=hsb.set
        )
        
        # 布局
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 绑定更多事件确保同步
        events_to_bind = [
            "<Key>", "<KeyRelease>", "<ButtonRelease>",
            "<MouseWheel>", "<Configure>", "<FocusIn>"
        ]
        for event in events_to_bind:
            self.editor.bind(event, self.update_line_numbers)
        
    def dual_scroll(self, *args):
        """同步滚动"""
        self.line_numbers.yview_moveto(args[0])
        self.editor.yview(*args)
        
    def on_text_scroll(self, first, last, scrollbar):
        self.line_numbers.yview_moveto(first)
        scrollbar.set(first, last)
        
    def update_line_numbers(self, event=None):
        """精确行号对齐"""
        # 获取可见区域
        first_visible_line = int(self.editor.index("@0,0").split('.')[0])
        last_visible_line = int(self.editor.index("@0,%d" % self.editor.winfo_height()).split('.')[0])
        
        # 计算实际内容
        content = self.editor.get(1.0, "end-1c")
        lines = content.split('\n')
        line_count = len(lines)
        
        # 生成带行号的文本
        line_nums = "\n".join(f"{i+1:>3}" for i in range(line_count))
        
        # 更新行号区域
        self.line_numbers.config(state="normal")
        self.line_numbers.delete(1.0, "end")
        self.line_numbers.insert(1.0, line_nums)
        self.line_numbers.config(state="disabled")
        
        # 动态调整行号宽度
        max_width = len(f"{max(line_count, 1):>3}") + 1
        self.line_numbers.config(width=max_width)
        
        # 同步滚动位置
        self.line_numbers.yview_moveto(self.editor.yview()[0])
        self.line_numbers.xview_moveto(0)
        
    def validate_input(self):
        """输入验证"""
        content = self.editor.get(1.0, "end-1c").strip()
        if not content:
            raise ValueError("输入内容不能为空")
            
        # 检查是否至少有一个轨道定义
        if "@track" not in content:
            raise ValueError("至少需要定义一个轨道 (@track instrument=...)")
        
    def get_output_path(self):
        user_path = self.output_path.get().strip()
        if user_path:
            return user_path
            
        os.makedirs(self.default_output_dir, exist_ok=True)
        base_name = "untitled"
        if self.input_path.get().strip():
            input_file = self.input_path.get().strip()
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            base_name = "".join(c for c in base_name if c.isalnum() or c in (' ', '_'))
            
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(
            self.default_output_dir,
            f"{base_name}_{timestamp}.mid"
        )
        
    def generate(self):
        try:
            self.validate_input()
            output_path = self.get_output_path()
            self.status(f"正在生成: {os.path.basename(output_path)}...")

            with tempfile.NamedTemporaryFile("w", delete=False, encoding='utf-8') as f:
                # 写入全局参数
                f.write(f"@tempo={self.tempo.get()}\n")
                f.write(f"@time_signature={self.time_num.get()}/{self.time_den.get()}\n")
                f.write(f"@key={self.key.get()}\n")
                f.write(self.editor.get(1.0, "end-1c"))
                temp_path = f.name
                
            metadata, tracks, warnings = parse_input(temp_path)
            create_midi(metadata, tracks, output_path)
            
            # 构建消息
            status_parts = [
                f"✅ 生成成功！",
                f"轨道数: {len(tracks)}",
                f"文件大小: {self.format_file_size(output_path)}"
            ]
            
            if warnings:
                status_parts.append(f"警告: {len(warnings)}条")
                messagebox.showwarning(
                    "生成警告",
                    "\n".join([f"• {w}" for w in warnings]),
                    detail=f"文件已生成: {output_path}"
                )
            
            self.status(" | ".join(status_parts))
            messagebox.showinfo(
                "生成完成",
                f"文件已保存到：\n{output_path}",
                detail=f"输出目录: {os.path.dirname(output_path)}"
            )
            
            # 打开输出目录
            if os.name == 'nt':
                os.startfile(os.path.dirname(output_path))
            else:
                os.system(f'open "{os.path.dirname(output_path)}"')
                
        except Exception as e:
            error_msg = str(e).split(":", 1)[-1].strip()
            self.status(f"❌ 错误: {error_msg}", error=True)
            messagebox.showerror(
                "生成失败",
                error_msg,
                detail="请检查：\n1. 输入内容有效性\n2. 文件权限\n3. 参数设置"
            )
        finally:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)
                
    def format_file_size(self, path):
        size = os.path.getsize(path)
        for unit in ['B', 'KB', 'MB']:
            if size < 1024.0:
                return f"{size:.1f}{unit}"
            size /= 1024.0
        return f"{size:.1f}GB"
        
    def status(self, text, error=False):
        self.status_bar.config(
            text=text,
            foreground="#dc3545" if error else "#28a745",
            font=('Consolas', 9, 'italic' if error else 'normal')
        )
        
    def setup_bindings(self):
        self.root.bind_all("<Control-o>", lambda e: self.browse_input())
        self.root.bind_all("<Control-s>", lambda e: self.generate())
        self.root.bind_all("<Alt-Up>", lambda e: self.editor.yview("scroll", -1, "units"))
        self.root.bind_all("<Alt-Down>", lambda e: self.editor.yview("scroll", 1, "units"))
        
    def browse_input(self):
        path = filedialog.askopenfilename(
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if path:
            self.input_path.delete(0, tk.END)
            self.input_path.insert(0, path)
            self.load_file(path)
            
    def browse_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".mid",
            filetypes=[("MIDI Files", "*.mid"), ("All Files", "*.*")]
        )
        if path:
            self.output_path.delete(0, tk.END)
            self.output_path.insert(0, path)
            
    def load_file(self, path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.editor.delete(1.0, tk.END)
                self.editor.insert(tk.END, f.read())
                self.update_line_numbers()
                self.status(f"已加载文件: {os.path.basename(path)}")
        except Exception as e:
            self.status(f"加载失败: {str(e)}", error=True)
            
    def clear_editor(self):
        self.editor.delete(1.0, tk.END)
        self.update_line_numbers()
        self.status("编辑器已清空")

if __name__ == "__main__":
    root = tk.Tk()
    app = NMNConverterApp(root)
    root.mainloop()