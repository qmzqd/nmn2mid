import os
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tempfile
import re
from nmn2midi_core import parse_input, create_midi

class EnhancedText(tk.Text):
    """带行号对齐优化的文本编辑器"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.line_numbers = None
        self.font = ('Consolas', 12)
        
    def sync_scroll(self, *args):
        if self.line_numbers:
            self.line_numbers.yview_moveto(args[0])

class SyntaxHighlighter:
    """改进的语法高亮系统"""
    def __init__(self, text_widget):
        self.text = text_widget
        self.text.tag_configure('meta', foreground='#007BFF')
        self.text.tag_configure('track', foreground='#28a745')
        self.text.tag_configure('comment', foreground='#6c757d')
        self.text.bind('<KeyRelease>', self.highlight)
        
    def highlight(self, event=None):
        self.clear_tags()
        self.highlight_line(r'@\w+\s*=\s*\S+', 'meta')
        self.highlight_line(r'$track.*$', 'track')
        self.highlight_line(r'#.*', 'comment')
        
    def highlight_line(self, pattern, tag):
        start = '1.0'
        while True:
            pos = self.text.search(pattern, start, 'end', 
                                 regexp=True, nocase=True)
            if not pos: break
            end = f"{pos} lineend"
            self.text.tag_add(tag, pos, end)
            start = end
            
    def clear_tags(self):
        for tag in ['meta', 'track', 'comment']:
            self.text.tag_remove(tag, '1.0', 'end')

class NMNConverterApp:
    def __init__(self, root):
        self.root = root
        root.title("NMN2MIDI Converter v2.1")
        root.geometry("1200x800")
        self.default_output_dir = os.path.join(os.getcwd(), "outputs")
        self.current_file = None
        self.setup_styles()
        self.setup_ui()
        self.setup_bindings()
        self.setup_events()
        
    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TLabel", font=('Segoe UI', 10))
        style.configure("TButton", font=('Segoe UI', 10), padding=6)
        
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 工具栏
        self.create_toolbar(main_frame)
        
        # 参数面板
        self.create_settings_panel(main_frame)
        
        # 编辑器区域
        self.create_editor_panel(main_frame)
        
        # 状态栏
        self.status_bar = ttk.Label(self.root, text="就绪", anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=5)
        
    def create_toolbar(self, parent):
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, pady=5)
        
        ttk.Button(toolbar, text="📂 打开", command=self.open_file).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="💾 保存", command=self.save_file).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="🎵 生成MIDI", command=self.generate).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="🧹 清空", command=self.clear_editor).pack(side=tk.LEFT, padx=3)

    def create_settings_panel(self, parent):
        settings_frame = ttk.LabelFrame(parent, text="全局设置", padding=10)
        settings_frame.pack(fill=tk.X, pady=10)
        
        # 参数控件
        ttk.Label(settings_frame, text="速度 (BPM):").grid(row=0, column=0, padx=5)
        self.tempo = ttk.Spinbox(settings_frame, from_=20, to=300, width=5)
        self.tempo.set(120)
        self.tempo.grid(row=0, column=1, padx=5)
        
        ttk.Label(settings_frame, text="拍号:").grid(row=0, column=2, padx=5)
        self.time_num = ttk.Combobox(settings_frame, values=["2","3","4","5","6","7"], width=3)
        self.time_num.set("4")
        self.time_num.grid(row=0, column=3, padx=5)
        ttk.Label(settings_frame, text="/").grid(row=0, column=4)
        self.time_den = ttk.Combobox(settings_frame, values=["2","4","8","16"], width=3)
        self.time_den.set("4")
        self.time_den.grid(row=0, column=5, padx=5)
        
        ttk.Label(settings_frame, text="调号:").grid(row=0, column=6, padx=5)
        self.key = ttk.Combobox(settings_frame, values=[
            "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"], width=3)
        self.key.set("C")
        self.key.grid(row=0, column=7, padx=5)

    def create_editor_panel(self, parent):
        editor_frame = ttk.Frame(parent)
        editor_frame.pack(fill=tk.BOTH, expand=True)
        
        # 行号栏
        self.line_numbers = tk.Text(
            editor_frame,
            width=4,
            padx=8,
            state="disabled",
            bg="#f8f9fa",
            font=('Consolas', 12),
            wrap=tk.NONE,
            spacing3=3  # 对齐行高
        )
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        
        # 主编辑器
        self.editor = EnhancedText(
            editor_frame,
            wrap=tk.NONE,
            font=('Consolas', 12),
            undo=True,
            padx=15,
            pady=15,
            bg="white",
            insertbackground="#007bff"
        )
        self.editor.line_numbers = self.line_numbers
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 滚动条
        vsb = ttk.Scrollbar(editor_frame, command=self.sync_scroll)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor.configure(yscrollcommand=lambda f, l: self.on_scroll(f, l, vsb))
        
        # 语法高亮
        self.highlighter = SyntaxHighlighter(self.editor)
        
    def setup_bindings(self):
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.editor.bind("<KeyRelease>", self.update_ui)
        self.editor.bind("<Key>", self.handle_key_events)  # 处理键盘事件
        self.editor.bind("<MouseWheel>", self.update_line_numbers)
        self.editor.bind("<Configure>", self.update_line_numbers)

    def handle_key_events(self, event):
        if event.keysym in ["BackSpace", "Return", "Tab"]:
            self.update_global_settings()  # 在特定的按键事件后更新全局设置

    def setup_events(self):
        for widget in [self.tempo, self.key, self.time_num, self.time_den]:
            widget.bind("<<ComboboxSelected>>", self.update_global_settings)
            
    def sync_scroll(self, *args):
        self.line_numbers.yview(*args)
        self.editor.yview(*args)
        
    def on_scroll(self, first, last, scrollbar):
        self.line_numbers.yview_moveto(first)
        scrollbar.set(first, last)
        self.update_line_numbers()
        
    def update_line_numbers(self, event=None):
        content = self.editor.get("1.0", "end-1c")
        lines = content.split('\n')
        line_nums = "\n".join(f"{i+1:>3}" for i in range(len(lines)))
        
        self.line_numbers.config(state="normal")
        self.line_numbers.delete("1.0", "end")
        self.line_numbers.insert("1.0", line_nums)
        self.line_numbers.config(state="disabled")
        
        # 精确同步滚动位置
        self.line_numbers.yview_moveto(self.editor.yview()[0])
        
    def update_ui(self, event=None):
        self.update_line_numbers()
        self.highlighter.highlight()
        self.update_global_settings()

    def update_global_settings(self, event=None):
        global_data = self.get_global_data()
        if global_data:
            self.tempo.set(global_data.get('@global_tempo', self.tempo.get()))
            self.key.set(global_data.get('@global_key', self.key.get()))
            self.time_num.set(global_data.get('@global_time_signature', '4/4').split('/')[0])
            self.time_den.set(global_data.get('@global_time_signature', '4/4').split('/')[1])
        
        self.replace_metadata_line('@global_tempo', f'@global_tempo={self.tempo.get()}')
        self.replace_metadata_line('@global_key', f'@global_key={self.key.get()}')
        self.replace_metadata_line('@global_time_signature',
                                   f'@global_time_signature={self.time_num.get()}/{self.time_den.get()}')

    def replace_metadata_line(self, pattern, new_line):
        content = self.editor.get("1.0", "end-1c")
        lines = content.split('\n')
        
        found = False
        for i in range(len(lines)):
            if lines[i].strip().startswith(pattern):
                lines[i] = new_line
                found = True
                break
        if not found:
            lines.insert(0, new_line)

        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", "\n".join(lines))
        
    def get_global_data(self):
        if self.current_file:
            with open(self.current_file, 'r', encoding='utf-8') as f:
                content = f.read()
                global_data = {}
                for line in content.splitlines():
                    if line.startswith('@global'):
                        key, value = line.split('=', 1)
                        global_data[key.strip()] = value.strip()
            return global_data
        return None

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
        if not self.current_file:
            self.current_file = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text Files", "*.txt")]
            )
        if self.current_file:
            try:
                content = self.editor.get("1.0", "end-1c")
                with open(self.current_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.status(f"文件已保存: {os.path.basename(self.current_file)}")
            except Exception as e:
                self.status(f"保存失败: {str(e)}", error=True)

    def clear_editor(self):
        self.editor.delete("1.0", "end")
        self.current_file = None
        self.update_ui()
        self.status("编辑器已清空")
        
    def generate(self):
        try:
            content = self.editor.get("1.0", "end-1c")
            if not content.strip():
                raise ValueError("输入内容不能为空")
                
            output_path = filedialog.asksaveasfilename(
                defaultextension=".mid",
                filetypes=[("MIDI Files", "*.mid")]
            )
            if not output_path:
                return
                
            with tempfile.NamedTemporaryFile("w", delete=False, encoding='utf-8') as f:
                f.write(content)
                temp_path = f.name
                
            metadata, tracks, warnings = parse_input(temp_path)
            create_midi(metadata, tracks, output_path)

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
        finally:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)

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
