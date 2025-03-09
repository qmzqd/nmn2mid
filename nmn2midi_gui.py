import os
import mido
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import tempfile
import re
from nmn2midi_core import parse_input, create_midi

class EnhancedText(tk.Text):
    """带行号对齐优化的文本编辑器"""
    def __init__(self, *args, **kwargs):
        kwargs.update({
            'wrap': tk.NONE,
            'font': ('Consolas', 12),
            'undo': True,
            'padx': 15,
            'pady': 15,
            'bg': "white",
            'insertbackground': "#007bff",
            'spacing3': 3  # 统一行间距
        })
        super().__init__(*args, **kwargs)
        self.line_numbers = None

class SyntaxHighlighter:
    """改进的语法高亮系统"""
    def __init__(self, text_widget, highlight_color):
        self.text = text_widget
        self.highlight_color = highlight_color
        self.update_tags()

    def update_tags(self):
        self.text.tag_configure('meta', foreground=self.highlight_color)
        self.text.tag_configure('track', foreground='#28a745')
        self.text.tag_configure('comment', foreground='#6c757d')
        self.text.bind('<KeyRelease>', self.highlight)

    def highlight(self, event=None):
        self.clear_tags()
        content = self.text.get("1.0", "end-1c")
        lines = content.split('\n')

        # 处理注释（优先处理）
        comment_pattern = re.compile(r'#.*$')
        for line_num, line in enumerate(lines, 1):
            for match in comment_pattern.finditer(line):
                start = f"{line_num}.{match.start()}"
                end = f"{line_num}.end"
                self.text.tag_add('comment', start, end)

        # 处理元数据
        meta_pattern = re.compile(r'@\w+\s*=\s*\S+')
        for line_num, line in enumerate(lines, 1):
            for match in meta_pattern.finditer(line):
                start = f"{line_num}.{match.start()}"
                end = f"{line_num}.{match.end()}"
                self.text.tag_add('meta', start, end)

        # 处理轨道行
        track_pattern = re.compile(r'^\[track.*', re.IGNORECASE)
        for line_num, line in enumerate(lines, 1):
            if track_pattern.match(line):
                start = f"{line_num}.0"
                end = f"{line_num}.end"
                self.text.tag_add('track', start, end)

    def clear_tags(self):
        for tag in ['meta', 'track', 'comment']:
            self.text.tag_remove(tag, '1.0', 'end')

class NMNConverterApp:
    def __init__(self, root):
        self.root = root
        root.title("NMN2MIDI Converter v1.0")
        root.geometry("1200x800")
        self.default_output_dir = os.path.join(os.getcwd(), "outputs")
        self.current_file = None
        self.highlight_color = "#007BFF"
        self.highlighter = None

        self.setup_styles()
        self.setup_ui()
        self.setup_bindings()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", font=('Segoe UI', 10))
        style.configure("TButton", font=('Segoe UI', 10), padding=6)

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.create_toolbar(main_frame)
        self.create_settings_panel(main_frame)
        self.create_editor_panel(main_frame)

        self.status_bar = ttk.Label(self.root, text="就绪", anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=5)

    def create_toolbar(self, parent):
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, pady=5)

        ttk.Button(toolbar, text="📂 打开", command=self.open_file).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="💾 保存", command=self.save_file).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="🎵 生成MIDI", command=self.generate).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="🧹 清空", command=self.clear_editor).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="⚙️ 设置", command=self.open_settings).pack(side=tk.RIGHT, padx=3)

    def open_settings(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title("设置")
        settings_window.geometry("300x200")

        ttk.Label(settings_window, text="选择高亮颜色：").pack(pady=10)
        ttk.Button(settings_window, text="选择颜色", command=self.choose_highlight_color).pack(pady=10)
        ttk.Button(settings_window, text="关于", command=self.show_about_info).pack(pady=10)

    def choose_highlight_color(self):
        color = colorchooser.askcolor(initialcolor=self.highlight_color)[1]
        if color:
            self.highlight_color = color
            self.highlighter.highlight_color = color
            self.highlighter.update_tags()
            messagebox.showinfo("成功", "高亮颜色已更新!")

    def show_about_info(self):
        messagebox.showinfo("关于", "简谱转MIDI转换器 v1.0\n开源项目，代码可以在GitHub上找到。")

    def create_settings_panel(self, parent):
        settings_frame = ttk.LabelFrame(parent, text="全局设置", padding=10)
        settings_frame.pack(fill=tk.X, pady=10)

        ttk.Label(settings_frame, text="速度 (BPM):").grid(row=0, column=0, padx=5)
        self.tempo = ttk.Spinbox(settings_frame, from_=20, to=300, width=5)
        self.tempo.set(120)
        self.tempo.grid(row=0, column=1, padx=5)

        ttk.Label(settings_frame, text="拍号:").grid(row=0, column=2, padx=5)
        self.time_num = ttk.Combobox(settings_frame, values=["2", "3", "4", "5", "6", "7"], width=3)
        self.time_num.set("4")
        self.time_num.grid(row=0, column=3, padx=5)
        ttk.Label(settings_frame, text="/").grid(row=0, column=4)
        self.time_den = ttk.Combobox(settings_frame, values=["2", "4", "8", "16"], width=3)
        self.time_den.set("4")
        self.time_den.grid(row=0, column=5)

        ttk.Label(settings_frame, text="调号:").grid(row=0, column=6, padx=5)
        self.key = ttk.Combobox(settings_frame, values=[ "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"], width=3)
        self.key.set("C")
        self.key.grid(row=0, column=7, padx=5)

    def create_editor_panel(self, parent):
        editor_frame = ttk.Frame(parent)
        editor_frame.pack(fill=tk.BOTH, expand=True)

        # 行号列（修复宽度为5字符）
        self.line_numbers = tk.Text(
            editor_frame,
            width=5,
            padx=8,
            state="disabled",
            bg="#f8f9fa",
            font=('Consolas', 12),
            wrap=tk.NONE,
            spacing3=3
        )
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        # 主编辑器
        self.editor = EnhancedText(editor_frame)
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 滚动条
        vsb = ttk.Scrollbar(editor_frame, command=self.sync_scroll)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor.configure(yscrollcommand=lambda f, l: self.on_scroll(f, l, vsb))

        self.highlighter = SyntaxHighlighter(self.editor, self.highlight_color)

    def setup_bindings(self):
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.editor.bind("<<Modified>>", self.on_text_modified)
        self.editor.bind("<Configure>", self.update_line_numbers)

    def on_text_modified(self, event=None):
        if self.editor.edit_modified():
            self.update_ui()
            self.editor.edit_modified(False)

    def sync_scroll(self, *args):
        """同步滚动条、编辑器和行号列的滚动位置"""
        self.editor.yview(*args)
        self.line_numbers.yview(*args)

    def on_scroll(self, first, last, scrollbar):
        """处理滚动事件"""
        self.line_numbers.yview_moveto(first)
        scrollbar.set(first, last)
        self.update_line_numbers()

    def update_line_numbers(self, event=None):
        """更新行号显示（增加滚动同步）"""
        content = self.editor.get("1.0", "end-1c")
        lines = content.split('\n')
        line_nums = "\n".join(f"{i + 1:>3}" for i in range(len(lines)))

        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", "end")
        self.line_numbers.insert("1.0", line_nums)
        self.line_numbers.config(state="disabled")
        
        # 强制同步滚动位置
        self.line_numbers.yview_moveto(self.editor.yview()[0])

    def update_ui(self, event=None):
        """更新界面元素"""
        self.update_line_numbers()
        self.highlighter.highlight()
        self.update_global_settings()

    def update_global_settings(self):
        """从编辑器内容更新全局设置"""
        global_data = self.get_global_data()
        if global_data:
            self.tempo.set(global_data.get('@global_tempo', self.tempo.get()))
            self.key.set(global_data.get('@global_key', self.key.get()))
            time_sig = global_data.get('@global_time_signature', '4/4').split('/')
            self.time_num.set(time_sig[0])
            self.time_den.set(time_sig[1])

        self.replace_metadata_line('@global_tempo', f'@global_tempo={self.tempo.get()}')
        self.replace_metadata_line('@global_key', f'@global_key={self.key.get()}')
        self.replace_metadata_line('@global_time_signature', 
                                 f'@global_time_signature={self.time_num.get()}/{self.time_den.get()}')

    def get_global_data(self):
        """从编辑器内容解析全局设置"""
        content = self.editor.get("1.0", "end-1c")
        global_data = {}
        for line in content.splitlines():
            if line.strip().startswith('@global'):
                parts = line.split('=', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    global_data[key] = value
        return global_data

    def replace_metadata_line(self, pattern_key, new_line):
        """替换或插入元数据行"""
        content = self.editor.get("1.0", "end-1c")
        lines = content.split('\n')
        found = False
        target_prefix = pattern_key + '='

        for i in range(len(lines)):
            if lines[i].strip().startswith(target_prefix):
                lines[i] = new_line
                found = True
                break
        
        if not found:
            lines.insert(0, new_line)

        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", '\n'.join(lines))

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.editor.delete("1.0", "end")
                    self.editor.insert("1.0", f.read())
                    self.current_file = path
                    self.update_ui()
                    self.status(f"已加载文件: {os.path.basename(path)}")
            except Exception as e:
                self.status(f"打开失败: {str(e)}", error=True)

    def save_file(self):
        if self.current_file:
            path = self.current_file
        else:
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text Files", "*.txt")]
            )
            if not path:
                return
            self.current_file = path

        try:
            content = self.editor.get("1.0", "end-1c")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.status(f"文件已保存: {os.path.basename(path)}")
        except Exception as e:
            self.status(f"保存失败: {str(e)}", error=True)

    def clear_editor(self):
        self.editor.delete("1.0", "end")
        self.current_file = None
        self.update_ui()
        self.status("编辑器已清空")

    def generate(self):
        try:
            content = self.editor.get("1.0", "end-1c").strip()
            if not content:
                raise ValueError("输入内容不能为空")
                
            output_path = filedialog.asksaveasfilename(
                defaultextension=".mid",
                filetypes=[("MIDI Files", "*.mid")]
            )
            if not output_path:
                return

            # 创建临时文件并写入内容
            with tempfile.NamedTemporaryFile("w", delete=False, encoding='utf-8') as f:
                f.write(content)
                temp_path = f.name
            
            # 解析输入内容
            global_meta, tracks, warnings = parse_input(temp_path)
            
            # 更新全局设置
            global_meta['tempo'] = mido.bpm2tempo(int(self.tempo.get()))
            numerator = int(self.time_num.get())
            denominator = int(self.time_den.get())
            global_meta['time_signature'] = (numerator, denominator)
            global_meta['key'] = self.key.get()
            
            # 生成MIDI文件
            create_midi(global_meta, tracks, output_path)

            # 清理临时文件
            if os.path.exists(temp_path):
                os.remove(temp_path)

            status_msg = [
                f"成功生成: {os.path.basename(output_path)}",
                f"轨道数: {len(tracks)}",
                f"文件大小: {self.get_file_size(output_path)}"
            ]
            
            if warnings:
                messagebox.showwarning("生成警告", "\n".join(warnings))

            self.status(" | ".join(status_msg))
            os.startfile(os.path.dirname(output_path))

        except Exception as e:
            self.status(f"生成错误: {str(e)}", error=True)
            messagebox.showerror("错误", str(e))

    def get_file_size(self, path):
        size = os.path.getsize(path)
        for unit in ['B', 'KB', 'MB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}GB"

    def status(self, text, error=False):
        self.status_bar.config(
            text=text,
            foreground="#dc3545" if error else "#28a745"
        )

if __name__ == "__main__":
    root = tk.Tk()
    app = NMNConverterApp(root)
    root.mainloop()