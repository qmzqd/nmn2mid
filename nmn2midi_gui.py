import os
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tempfile
from nmn2midi import parse_input, create_midi

class NMNConverterApp:
    def __init__(self, root):
        self.root = root
        root.title("NMN2MIDI Converter v1.0")
        root.geometry("1100x750")
        self.default_output_dir = os.path.join(os.getcwd(), "outputs")
        self.setup_ui()
        self.setup_bindings()
        
    def setup_ui(self):
        """初始化界面组件"""
        # 样式配置
        style = ttk.Style()
        style.configure("TLabel", font=('Segoe UI', 10))
        style.configure("TButton", font=('Segoe UI', 10))
        style.configure("Status.TLabel", font=('Segoe UI', 9), foreground="#666")
        
        # 主布局框架
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 文件控制区
        self.create_file_controls(main_frame)
        
        # 参数设置区
        self.create_settings_panel(main_frame)
        
        # 编辑区
        self.create_editor(main_frame)
        
        # 状态栏
        self.status_bar = ttk.Label(self.root, style="Status.TLabel", anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=5)
        
        # 提示标签
        self.tip_label = ttk.Label(
            self.root,
            text="💡 提示：可以使用拖放操作导入文件 | Ctrl+S 快速生成",
            style="Status.TLabel"
        )
        self.tip_label.pack(side=tk.BOTTOM, fill=tk.X, padx=15)
        
    def create_file_controls(self, parent):
        """文件操作组件"""
        frame = ttk.LabelFrame(parent, text="文件操作", padding=10)
        frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=5)
        
        # 输入文件
        ttk.Label(frame, text="输入文件:").grid(row=0, column=0, sticky="w")
        self.input_path = ttk.Entry(frame, width=60)
        self.input_path.grid(row=0, column=1, padx=5, sticky="ew")
        ttk.Button(frame, text="浏览", command=self.browse_input, width=8).grid(row=0, column=2)
        
        # 输出文件
        ttk.Label(frame, text="输出文件:").grid(row=1, column=0, sticky="w")
        self.output_path = ttk.Entry(frame, width=60)
        self.output_path.grid(row=1, column=1, padx=5, sticky="ew")
        ttk.Button(frame, text="浏览", command=self.browse_output, width=8).grid(row=1, column=2)
        
        # 操作按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=3, pady=10)
        ttk.Button(btn_frame, text="🎵 生成MIDI", command=self.generate, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🧹 清空", command=self.clear_editor, width=8).pack(side=tk.LEFT)
        
        # 设置列权重
        frame.columnconfigure(1, weight=1)
        
    def create_settings_panel(self, parent):
        """参数设置面板"""
        frame = ttk.LabelFrame(parent, text="乐曲参数", padding=10)
        frame.grid(row=1, column=0, sticky="nsew", pady=5)
        
        # 速度
        ttk.Label(frame, text="速度 (BPM):").grid(row=0, column=0, sticky="w")
        self.tempo = ttk.Spinbox(frame, from_=20, to=300, width=5)
        self.tempo.set(120)
        self.tempo.grid(row=0, column=1, padx=5)
        
        # 拍号
        ttk.Label(frame, text="拍号:").grid(row=0, column=2, sticky="w", padx=10)
        self.time_num = ttk.Combobox(frame, values=["2","3","4","5","6","7"], width=3)
        self.time_num.set("4")
        self.time_num.grid(row=0, column=3)
        ttk.Label(frame, text="/").grid(row=0, column=4)
        self.time_den = ttk.Combobox(frame, values=["2","4","8","16"], width=3)
        self.time_den.set("4")
        self.time_den.grid(row=0, column=5)
        
        # 调号
        ttk.Label(frame, text="调号:").grid(row=0, column=6, sticky="w", padx=10)
        self.key = ttk.Combobox(frame, values=[
            "C", "C#", "D", "D#", "E", "F", 
            "F#", "G", "G#", "A", "A#", "B"
        ], width=3)
        self.key.set("C")
        self.key.grid(row=0, column=7)
        
        # 乐器
        ttk.Label(frame, text="乐器:").grid(row=0, column=8, sticky="w", padx=10)
        self.instrument = ttk.Combobox(frame, values=[
            "0: 钢琴", "1: 明亮钢琴", "25: 钢弦吉他",
            "40: 小提琴", "56: 小号", "74: 长笛"
        ], width=15)
        self.instrument.set("0: 钢琴")
        self.instrument.grid(row=0, column=9)
        
    def create_editor(self, parent):
        """乐谱编辑器"""
        frame = ttk.LabelFrame(parent, text="乐谱编辑器", padding=10)
        frame.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=5)
        
        # 添加行号
        self.line_numbers = tk.Text(frame, width=4, padx=4, takefocus=0, border=0,
                                   background="#f0f0f0", state="disabled")
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        
        self.editor = tk.Text(frame, wrap=tk.NONE, font=('Consolas', 12), 
                            undo=True, padx=10, pady=10)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.editor.xview)
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.editor.yview)
        self.editor.configure(xscrollcommand=hsb.set, yscrollcommand=vsb.set)
        
        # 布局
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 绑定事件更新行号
        self.editor.bind("<KeyRelease>", self.update_line_numbers)
        self.editor.bind("<MouseWheel>", self.update_line_numbers)
        self.editor.bind("<Configure>", self.update_line_numbers)
        
    def update_line_numbers(self, event=None):
        """更新行号显示"""
        lines = self.editor.get(1.0, "end-1c").split("\n")
        line_nums = "\n".join(str(i+1) for i in range(len(lines)))
        self.line_numbers.config(state="normal")
        self.line_numbers.delete(1.0, tk.END)
        self.line_numbers.insert(1.0, line_nums)
        self.line_numbers.config(state="disabled")
        
    def get_output_path(self):
        """智能生成输出路径"""
        user_path = self.output_path.get().strip()
        if user_path:
            return user_path
            
        # 自动生成路径
        if not os.path.exists(self.default_output_dir):
            os.makedirs(self.default_output_dir)
            
        input_file = self.input_path.get().strip()
        if input_file:
            base_name = os.path.splitext(os.path.basename(input_file))[0]
            base_name = "".join(c for c in base_name if c.isalnum() or c in (' ', '_'))
        else:
            base_name = "untitled"
            
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return os.path.join(
            self.default_output_dir,
            f"{base_name}_{timestamp}.mid"
        )
        
    def generate(self):
        """生成MIDI"""
        try:
            output_path = self.get_output_path()
            self.status(f"准备生成: {os.path.basename(output_path)}...")
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile("w", delete=False, encoding='utf-8') as f:
                # 写入元数据
                f.write(f"@tempo={self.tempo.get()}\n")
                f.write(f"@time_signature={self.time_num.get()}/{self.time_den.get()}\n")
                f.write(f"@key={self.key.get()}\n")
                f.write(f"@instrument={self.instrument.get().split(':')[0]}\n")
                f.write(self.editor.get(1.0, tk.END))
                temp_path = f.name
                
            # 调用核心逻辑
            metadata, notes, warnings = parse_input(temp_path)
            create_midi(metadata, notes, output_path)
            
            # 显示结果
            msg = [
                f"✅ 生成成功！",
                f"文件路径: {output_path}",
                f"文件大小: {self.format_file_size(output_path)}"
            ]
            if warnings:
                msg.append("\n⚠ 注意:")
                msg.extend(warnings)
                
            self.status(" | ".join(msg))
            messagebox.showinfo(
                "生成完成", 
                "\n".join(msg),
                detail=f"输出目录: {os.path.dirname(output_path)}"
            )
            
            # 自动打开输出目录
            if os.name == 'nt':
                os.startfile(os.path.dirname(output_path))
            else:
                os.system(f'open "{os.path.dirname(output_path)}"')
                
        except Exception as e:
            self.status(f"❌ 生成失败: {str(e)}", error=True)
            messagebox.showerror(
                "错误",
                str(e),
                detail=f"请检查：\n1. 乐谱格式\n2. 文件写入权限\n3. 参数有效性"
            )
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    def format_file_size(self, file_path):
        """格式化文件大小为人类可读的字符串"""
        size_bytes = os.path.getsize(file_path)
        if size_bytes == 0:
            return "0 B"
        size_units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        while size_bytes >= 1024 and unit_index < len(size_units) - 1:
            size_bytes /= 1024.0
            unit_index += 1
        return f"{size_bytes:.2f} {size_units[unit_index]}"
        
    def status(self, text, error=False):
        """更新状态栏"""
        self.status_bar.config(
            text=text,
            foreground="#dc3545" if error else "#28a745",
            font=('Segoe UI', 9, 'italic' if error else 'normal')
        )
        
    def setup_bindings(self):
        """设置事件绑定"""
        self.root.bind_all("<Control-o>", lambda e: self.browse_input())
        self.root.bind_all("<Control-s>", lambda e: self.generate())
        
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
                content = f.read()
                self.editor.delete(1.0, tk.END)
                self.editor.insert(tk.END, content)
                self.status("文件已加载: " + os.path.basename(path))
        except Exception as e:
            self.status("错误: " + str(e), error=True)
            
    def clear_editor(self):
        self.editor.delete(1.0, tk.END)
        self.status("编辑器已清空")

if __name__ == "__main__":
    root = tk.Tk()
    app = NMNConverterApp(root)
    root.mainloop()