# 简谱转MIDI转换器

将简谱文本文件转换为标准MIDI文件，支持全部调号、拍号、速度和乐器设置。自动处理音符时值与八度偏移。

## 功能特性

- **智能默认值**：自动补全未设置的元数据参数并提示用户
- **简谱语法支持**：支持音符（1-7）、休止符（0）、升降号（#/b）、八度调整（^/_）、时值控制（-/.）
- **参数配置**：可设置速度（BPM）、拍号、调号、MIDI乐器
- **批量处理**：支持通过命令行参数指定输入/输出文件
- **多轨支持**：可以在输入文件中定义多个轨道，每个轨道可以有不同的乐器、速度等设置
- **歌词支持**：可以在音符中添加歌词，生成的MIDI文件中会包含歌词事件

## 安装

1. 安装Python 3.8+
2. 安装依赖库：
```bash
pip install mido
```

## 输入文件格式

创建`.txt`文件，格式示例：
```text
@global_tempo=90
@global_time_signature=3/4
@global_key=G
@global_instrument=0

[track]
@tempo=120
@time_signature=4/4
@key=C
@instrument=25

1 "Hello" 2 "World" | 5_ "Low" 0 "Pause"

[track]
@instrument=41

5- 3. ^1 0 2_
```

### 全局元数据配置（可选）
| 指令                | 默认值     | 说明                  |
|---------------------|-----------|----------------------|
| `@global_tempo=BPM`        | 120 BPM   | 每分钟拍数           |
| `@global_time_signature=N/D` | 4/4      | 拍号（分子/分母）     |
| `@global_key=KEY`          | C大调     | 调号（支持升降号）    |
| `@global_instrument=ID`    | 0 (钢琴)  | MIDI乐器编号（0-127）|

### 轨道配置
- 使用`[track]`分隔不同的轨道
- 每个轨道可以单独设置元数据，格式与全局元数据相同，但以`@`开头
- 轨道中的元数据会覆盖全局设置

### 音符语法
| 符号 | 示例      | 作用                      | 说明                  |
|------|-----------|--------------------------|----------------------|
| 1-7  | `5`       | 基础音符                 | 对应调式音阶         |
| 0    | `0`       | 休止符                   | 时长为1拍            |
| #    | `#4`      | 升半音                   | 写在数字前           |
| b    | `b7`      | 降半音                   | 写在数字前           |
| ^    | `^1`/`5^^`| 升八度（每符号+1八度）   | 可叠加使用           |
| _    | `_5`/`3__`| 降八度（每符号-1八度）   | 可叠加使用           |
| -    | `5-`      | 延长时值（×2）           | 可叠加：`5--`=4拍    |
| .    | `3.`      | 附点时值（×1.5）         | 可叠加：`5..`=2.25拍 |

### 歌词功能
在音符中添加歌词，使用双引号（"）包围歌词文本。例如：
```text
1 "Hello" 2 "World"
```
这表示在第一个音符（1）处添加歌词"Hello"，在第二个音符（2）处添加歌词"World"。转换器会将歌词与音符一起处理，并在生成的MIDI轨道中添加对应的歌词事件。

## 使用说明

### 基本命令
```bash
# 使用所有默认参数
python nmn2midi.py input.txt

# 指定输出文件
python nmn2midi.py input.txt -o output.mid
```

### 运行示例
当输入文件包含多个轨道时：
```bash
正在解析文件: demo.txt

配置提示:
  * 使用全局 tempo：90 BPM
  * 轨道1使用自定义 tempo：120 BPM
  * 轨道2使用全局 tempo：90 BPM

解析到 2 个轨道
开始生成MIDI...
成功生成: output.mid
```

### 错误处理
程序会检测以下错误并终止运行：
- 无效调号（如`@key=H`）
- 乐器编号超出范围（如`@instrument=128`）
- 非法音符格式（如`8`、`#9`）
- 文件路径错误

## 支持的乐器
完整列表参考[通用MIDI乐器表](https://www.midi.org/specifications-old/item/gm-level-1-sound-set)，常用乐器包括：

| ID  | 乐器       | ID  | 乐器       |
|-----|-----------|-----|-----------|
| 0   | 钢琴       | 41  | 小提琴     |
| 25  | 钢弦吉他   | 56  | 小号       |
| 33  | 电贝司     | 74  | 长笛       |
| 48  | 弦乐合奏   | 127 | 枪声特效   |

(仅列出部分常用乐器，本工具支持1~127范围内的乐器编号)

## 智能路径规则

1. **默认输出目录**：
   - 自动在程序所在目录创建`outputs`文件夹
   - 未指定输出路径时在此生成文件

2. **自动命名规则**：
   - 格式：`[输入文件名]_[年月日_时分秒].mid`
   - 示例：`mysong_20231010_153045.mid`

3. **特殊处理**：
   - 自动过滤非法文件名字符
   - 支持文件路径拖放操作
   - 生成后自动打开输出目录

## 新增提示系统

- 底部状态栏实时反馈
- 生成完成提示
- 错误提示包含：
  - 具体错误原因
  - 常见问题排查建议
  - 错误代码位置参考

## 常见错误示例

1. **单独使用时值符号**：
   - 无效，必须跟在音符后面
   - 空格使用不规范：
     - `5 -` 应写为 `5-`
     - `3 .` 应写为 `3.`
   - 无效的升降号位置：
     - `4#` 应写为 `#4`
     - `b` 缺少音符数字

在"音符语法"章节增加红色警告框：

| -    | `5-`      | 延长时值（×2）           | 可叠加：`5--`=4拍    |
| .    | `3.`      | 附点时值（×1.5）         | 可叠加：`5..`=2.25拍 |

> ⚠ 注意：时值符号必须**紧接音符**，中间不能有空格。多个音符之间用空格分隔。
>
> ✅ 正确写法：`5- 3. ^1`  
> ❌ 错误写法：`5 - 3 . ^ 1`

## 许可协议
本项目采用 [GPL License](LICENSE)