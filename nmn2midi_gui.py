import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.font import Font
import tempfile
import os
from nmn2midi_core import parse_input, create_midi

class LineNumberCanvas(tk.Canvas):
    """带自动刷新的行号面板"""
    def __init__(self, master, text_widget, **kwargs):
        super().__init__(master, **kwargs)
        self.text_widget = text_widget
        self.font = Font(family='Consolas', size=12)
        self.bind('<Configure>', self._redraw)
        self.text_widget.bind('<KeyRelease>', self._redraw)
        self.text_widget.bind('<ButtonRelease>', self._redraw)
    
    def _redraw(self, event=None):
        self.delete('all')
        width = self.winfo_width()
        i = self.text_widget.index('@0,0')
        while True:
            dline = self.text_widget.dlineinfo(i)
            if dline is None: break
            y = dline[1]
            line_num = str(i).split('.')[0]
            self.create_text(
                width-5, y,
                anchor='ne',
                text=line_num,
                font=self.font,
                fill='#666'
            )
            i = self.text_widget.index(f'{i}+1line')

class SyntaxHighlighter:
    """实时语法高亮"""
    def __init__(self, text_widget):
        self.text = text_widget
        self.text.tag_configure('meta', foreground='#007BFF')
        self.text.tag_configure('track', foreground='#28a745', font=('Consolas', 12, 'bold'))
        self.text.tag_configure('comment', foreground='#6c757d')
        self.text.tag_configure('error', background='#ffe5e5')
        self.text.bind('<KeyRelease>', self.highlight)
    
    def highlight(self, event=None):
        self._clear_tags()
        self._highlight_pattern(r'@\w+', 'meta')
        self._highlight_pattern(r'\[track\]', 'track')
        self._highlight_pattern(r'#.*', 'comment')
    
    def _highlight_pattern(self, pattern, tag):
        start = '1.0'
        while True:
            pos = self.text.search(pattern, start, stopindex='end', regexp=True)
            if not pos: break
            end = f"{pos}+{len(self.text.get(pos, f'{pos} lineend'))}c"
            self.text.tag_add(tag, pos, end)
            start = end
    
    def _clear_tags(self):
        for tag in ['meta', 'track', 'comment', 'error']:
            self.text.tag_remove(tag, '1.0', 'end')

class NMNConverterApp:
    def __init__(self, root):
        self.root = root
        root.title("简谱转MIDI工具 v2.0")
        root.geometry("1200x800")
        self._setup_ui()
        self.current_file = None
    
    def _setup_ui(self):
        # 主布局
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 工具栏
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=5)
        
        ttk.Button(toolbar, text="打开", command=self._open_file).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="保存", command=self._save_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="生成MIDI", command=self._generate).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="退出", command=self.root.quit).pack(side=tk.RIGHT)
        
        # 编辑区域
        editor_frame = ttk.Frame(main_frame)
        editor_frame.pack(fill=tk.BOTH, expand=True)
        
        # 文本编辑器
        self.editor = tk.Text(
            editor_frame,
            wrap=tk.NONE,
            font=('Consolas', 12),
            undo=True,
            padx=10,
            pady=10
        )
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 行号面板
        self.line_numbers = LineNumberCanvas(
            editor_frame, 
            text_widget=self.editor,
            width=60,
            bg='#f8f9fa',
            highlightthickness=0
        )
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        
        # 语法高亮
        self.highlighter = SyntaxHighlighter(self.editor)
        
        # 滚动条
        vsb = ttk.Scrollbar(editor_frame, command=self._on_scroll)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.editor.configure(yscrollcommand=vsb.set)
        
        # 状态栏
        self.status = ttk.Label(
            self.root,
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=('Consolas', 10)
        )
        self.status.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 绑定事件
        self.editor.bind('<Control-o>', lambda e: self._open_file())
        self.editor.bind('<Control-s>', lambda e: self._save_file())
        self.editor.bind('<Control-g>', lambda e: self._generate())
    
    def _on_scroll(self, *args):
        self.editor.yview(*args)
        self.line_numbers._redraw()
    
    def _open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.editor.delete('1.0', tk.END)
                    self.editor.insert('1.0', f.read())
                self.current_file = path
                self._update_status(f"已加载文件: {os.path.basename(path)}")
            except Exception as e:
                messagebox.showerror("打开失败", str(e))
    
    def _save_file(self):
        if not self.current_file:
            self._save_file_as()
            return
        
        try:
            content = self.editor.get('1.0', tk.END)
            with open(self.current_file, 'w', encoding='utf-8') as f:
                f.write(content)
            self._update_status(f"文件已保存: {self.current_file}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
    
    def _save_file_as(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if path:
            self.current_file = path
            self._save_file()
    
    def _generate(self):
        content = self.editor.get('1.0', tk.END)
        if not content.strip():
            messagebox.showwarning("空内容", "请输入有效的简谱内容")
            return
        
        try:
            # 临时文件处理
            with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as f:
                f.write(content)
                temp_path = f.name
            
            global_meta, tracks, warnings = parse_input(content)
            
            # 保存对话框
            output_path = filedialog.asksaveasfilename(
                defaultextension=".mid",
                filetypes=[("MIDI Files", "*.mid"), ("All Files", "*.*")]
            )
            if output_path:
                create_midi(global_meta, tracks, output_path)
                
                # 显示生成结果
                success_msg = [
                    f"成功生成: {os.path.basename(output_path)}",
                    f"轨道数: {len(tracks)}",
                    f"文件大小: {self._format_size(os.path.getsize(output_path))}"
                ]
                self._update_status(" | ".join(success_msg))
                
                # 显示警告
                if warnings:
                    msg = "\n".join(warnings)
                    messagebox.showwarning(
                        "生成警告",
                        f"检测到{len(warnings)}条警告:\n{msg}",
                        detail=f"文件已保存到:\n{output_path}"
                    )
                
                # 打开所在文件夹
                if messagebox.askyesno("打开文件夹", "是否打开输出目录？"):
                    os.startfile(os.path.dirname(output_path))
        
        except Exception as e:
            self._show_error(str(e))
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} GB"
    
    def _update_status(self, text, error=False):
        self.status.config(
            text=text,
            foreground='#dc3545' if error else '#28a745'
        )
    
    def _show_error(self, message):
        self._update_status(f"错误: {message}", error=True)
        messagebox.showerror(
            "生成失败",
            message,
            detail="请检查：\n1. 输入格式是否正确\n2. 参数设置是否合法\n3. 文件权限"
        )

if __name__ == '__main__':
    root = tk.Tk()
    app = NMNConverterApp(root)
    root.mainloop()