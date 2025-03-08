import mido
import re
import argparse
from mido import MidiFile, MidiTrack, Message, MetaMessage

# 调号到MIDI基音的映射
KEY_TO_BASE = {
    'C': 60, 'C#': 61, 'Db': 61, 'D': 62, 'D#': 63, 'Eb': 63,
    'E': 64, 'F': 65, 'F#': 66, 'Gb': 66, 'G': 67, 'G#': 68,
    'Ab': 68, 'A': 69, 'A#': 70, 'Bb': 70, 'B': 71
}

# 大调音阶半音偏移量（1-7对应的音程）
SCALE_DEGREES = [0, 2, 4, 5, 7, 9, 11]

def parse_input(file_path):
    """解析输入文件并返回元数据、音符列表和警告信息"""
    default_values = {
        'tempo': mido.bpm2tempo(120),
        'time_signature': (4, 4),
        'key': 'C',
        'instrument': 0,
        'ticks_per_beat': 480
    }
    metadata = default_values.copy()
    provided = {k: False for k in ['tempo', 'time_signature', 'key', 'instrument']}
    notes = []
    warnings = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('@'):
                try:
                    key, value = line[1:].split('=', 1)
                    key = key.lower()
                    if key == 'tempo':
                        metadata['tempo'] = mido.bpm2tempo(int(value))
                        provided['tempo'] = True
                    elif key == 'time_signature':
                        n, d = map(int, value.split('/'))
                        metadata['time_signature'] = (n, d)
                        provided['time_signature'] = True
                    elif key == 'key':
                        if value.strip() not in KEY_TO_BASE:
                            raise ValueError(f"无效调号: {value}")
                        metadata['key'] = value.strip()
                        provided['key'] = True
                    elif key == 'instrument':
                        program = int(value)
                        if program < 0 or program > 127:
                            raise ValueError("乐器编号必须在0-127之间")
                        metadata['instrument'] = program
                        provided['instrument'] = True
                except Exception as e:
                    raise ValueError(f"元数据解析错误: {line} - {str(e)}")
            else:
                notes.extend(line.split())
    
    # 生成未设置参数的警告
    for param in provided:
        if not provided[param]:
            if param == 'tempo':
                value = f"{mido.tempo2bpm(default_values['tempo'])} BPM"
            elif param == 'time_signature':
                value = f"{default_values['time_signature'][0]}/{default_values['time_signature'][1]}"
            elif param == 'key':
                value = f"{default_values['key']} 大调"
            elif param == 'instrument':
                value = f"{default_values['instrument']} (钢琴)"
            warnings.append(f"未设置 {param}，使用默认值：{value}")
    
    return metadata, notes, warnings

def parse_note(note_str, key):
    """解析单个音符字符串"""
    if note_str.startswith('0'):
        # 处理休止符
        match = re.match(r'^0([.-]*)$', note_str)
        if not match:
            raise ValueError(f"无效休止符: {note_str}")
        duration = 1.0
        modifiers = match.group(1)
        for c in modifiers:
            duration *= 2 if c == '-' else 1.5
        return (None, duration)
    
    # 解析音符元素
    match = re.match(r'^([#b]?)(\d)([_^]*)([.-]*)$', note_str)
    if not match:
        raise ValueError(f"无效音符格式: {note_str}")
    
    accidental, num, octave_mod, duration_mod = match.groups()
    num = int(num)
    if num < 1 or num > 7:
        raise ValueError(f"无效音符数字: {num}")

    # 计算基础音高
    try:
        base_pitch = KEY_TO_BASE[key.upper()]
    except KeyError:
        raise ValueError(f"无效调号: {key}")

    # 计算半音偏移
    semitone = SCALE_DEGREES[num - 1]
    if accidental == '#':
        semitone += 1
    elif accidental == 'b':
        semitone -= 1

    # 计算八度偏移
    octave = 0
    for c in octave_mod:
        if c == '^': octave += 1
        elif c == '_': octave -= 1

    # 计算最终音高
    midi_pitch = base_pitch + semitone + (octave * 12)
    if midi_pitch < 0 or midi_pitch > 127:
        raise ValueError(f"音高超出范围(0-127): {midi_pitch}")

    # 计算时值
    duration = 1.0
    for c in duration_mod:
        duration *= 2 if c == '-' else 1.5
    
    return (midi_pitch, duration)

def create_midi(metadata, notes, output_file):
    """生成MIDI文件"""
    mid = MidiFile(ticks_per_beat=metadata['ticks_per_beat'])
    track = MidiTrack()
    mid.tracks.append(track)

    # 添加元数据
    track.append(MetaMessage('set_tempo', 
                           tempo=metadata['tempo'], 
                           time=0))
    track.append(MetaMessage('time_signature',
                           numerator=metadata['time_signature'][0],
                           denominator=metadata['time_signature'][1],
                           time=0))
    track.append(Message('program_change',
                       program=metadata['instrument'],
                       time=0))

    # 收集所有MIDI事件
    events = []
    current_time = 0  # 当前绝对时间（tick）

    for note_str in notes:
        try:
            pitch, duration = parse_note(note_str, metadata['key'])
        except Exception as e:
            raise ValueError(f"解析音符失败: {note_str} - {str(e)}")
        
        ticks = int(duration * metadata['ticks_per_beat'])
        
        if pitch is None:  # 休止符
            current_time += ticks
        else:  # 音符
            # 添加音符开启事件
            events.append(('note_on', pitch, current_time))
            # 添加音符关闭事件
            events.append(('note_off', pitch, current_time + ticks))
            current_time += ticks

    # 按时间排序事件
    events.sort(key=lambda x: x[2])

    # 转换为增量时间并写入轨道
    last_time = 0
    for event in events:
        delta = event[2] - last_time
        track.append(Message(event[0], 
                     note=event[1], 
                     velocity=64, 
                     time=delta))
        last_time = event[2]

    # 处理结尾的休止符时间
    if current_time > last_time:
        delta = current_time - last_time
        track.append(MetaMessage('end_of_track', time=delta))
    else:
        track.append(MetaMessage('end_of_track', time=0))

    mid.save(output_file)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='简谱转MIDI转换器 v1.0',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog='示例:\n  python nmn2midi.py input.txt -o output.mid'
    )
    parser.add_argument('input_file', help='输入文本文件路径')
    parser.add_argument('-o', '--output', 
                       default='output.mid',
                       help='输出MIDI文件路径（默认: output.mid）')
    
    args = parser.parse_args()
    
    try:
        print(f"正在解析文件: {args.input_file}")
        metadata, notes, warnings = parse_input(args.input_file)
        
        # 显示未设置参数的提示
        if warnings:
            print("\n配置提示:")
            for warn in warnings:
                print(f"  * {warn}")
            print()
        
        print(f"解析到 {len(notes)} 个音符/休止符")
        print("开始生成MIDI...")
        create_midi(metadata, notes, args.output)
        print(f"成功生成: {args.output}")
    except Exception as e:
        print(f"\n错误: {str(e)}")
        print("生成失败，请检查输入文件格式")
        exit(1)