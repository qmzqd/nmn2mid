# File 1: nmn2midi_core.py(核心功能)
import mido
import re
import copy
import argparse
from mido import MidiFile, MidiTrack, Message, MetaMessage

# 调号到MIDI基音的映射
KEY_TO_BASE = {
    'C': 60, 'C#': 61, 'Db': 61, 'D': 62, 'D#': 63, 'Eb': 63,
    'E': 64, 'F': 65, 'F#': 66, 'Gb': 66, 'G': 67, 'G#': 68,
    'Ab': 68, 'A': 69, 'A#': 70, 'Bb': 70, 'B': 71
}

SCALE_DEGREES = [0, 2, 4, 5, 7, 9, 11]  # 大调音阶半音偏移量

def parse_input(content):
    """解析输入内容并返回全局元数据、轨道列表和警告信息"""
    global_defaults = {
        'tempo': mido.bpm2tempo(120),
        'time_signature': (4, 4),
        'key': 'C',
        'instrument': 0,
        'ticks_per_beat': 480
    }
    tracks = []
    current_track = None
    in_global_section = True
    warnings = []
    
    lines = content.split('\n')
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # 处理轨道定义
        if line.startswith('['):
            if line.lower().startswith('[track'):
                current_track = {
                    'metadata': copy.deepcopy(global_defaults),
                    'provided': {'tempo': False, 'time_signature': False, 
                                'key': False, 'instrument': False},
                    'notes': []
                }
                in_global_section = False
                tracks.append(current_track)
            continue
        
        # 处理全局元数据
        if in_global_section and line.startswith('@'):
            try:
                key_part = line[1:].split('#')[0].strip()  # 忽略注释
                key, value = key_part.split('=', 1)
                key = key.lower().replace('global_', '')
                
                if key == 'tempo':
                    global_defaults['tempo'] = mido.bpm2tempo(int(value))
                elif key == 'time_signature':
                    numerator, denominator = map(int, value.split('/'))
                    global_defaults['time_signature'] = (numerator, denominator)
                elif key == 'key':
                    if value not in KEY_TO_BASE:
                        raise ValueError(f"无效调号: {value}")
                    global_defaults['key'] = value
                elif key == 'instrument':
                    program = int(value)
                    if not 0 <= program <= 127:
                        raise ValueError("乐器编号超出范围 (0-127)")
                    global_defaults['instrument'] = program
                else:
                    warnings.append(f"第{line_num}行: 未知的全局参数 '{key}'")
                    
            except Exception as e:
                raise ValueError(f"第{line_num}行全局参数错误: {str(e)}")
        
        # 处理轨道元数据
        elif current_track is not None and line.startswith('@'):
            try:
                key_part = line[1:].split('#')[0].strip()  # 忽略注释
                key, value = key_part.split('=', 1)
                key = key.lower()
                
                if key == 'tempo':
                    current_track['metadata']['tempo'] = mido.bpm2tempo(int(value))
                    current_track['provided']['tempo'] = True
                elif key == 'time_signature':
                    numerator, denominator = map(int, value.split('/'))
                    current_track['metadata']['time_signature'] = (numerator, denominator)
                    current_track['provided']['time_signature'] = True
                elif key == 'key':
                    if value not in KEY_TO_BASE:
                        raise ValueError(f"无效调号: {value}")
                    current_track['metadata']['key'] = value
                    current_track['provided']['key'] = True
                elif key == 'instrument':
                    program = int(value)
                    if not 0 <= program <= 127:
                        raise ValueError("乐器编号超出范围 (0-127)")
                    current_track['metadata']['instrument'] = program
                    current_track['provided']['instrument'] = True
                else:
                    warnings.append(f"第{line_num}行: 未知的轨道参数 '{key}'")
                    
            except Exception as e:
                raise ValueError(f"第{line_num}行轨道参数错误: {str(e)}")
        
        # 处理音符行
        elif current_track is not None:
            current_track['notes'].extend(line.split())
    
    # 生成警告信息
    for track_idx, track in enumerate(tracks, 1):
        for param in ['tempo', 'time_signature', 'key', 'instrument']:
            if not track['provided'][param]:
                default_value = track['metadata'][param]
                description = {
                    'tempo': f"{mido.tempo2bpm(default_value)} BPM",
                    'time_signature': f"{default_value[0]}/{default_value[1]}",
                    'key': f"{default_value}大调",
                    'instrument': f"{default_value}"
                }[param]
                warnings.append(f"轨道 {track_idx}: 使用全局{param} ({description})")
    
    return global_defaults, tracks, warnings

def parse_note(note_str, key):
    """解析单个音符字符串"""
    if note_str.startswith('0'):
        match = re.fullmatch(r'0([.-]*)', note_str)
        if not match:
            raise ValueError(f"无效休止符格式: {note_str}")
        duration = 1.0
        for c in match.group(1):
            duration *= 2 if c == '-' else 1.5
        return None, duration
    
    match = re.fullmatch(r'([#b]?)([1-7])([_^]*)([.-]*)', note_str)
    if not match:
        raise ValueError(f"无效音符格式: {note_str}")
    
    accidental, degree, octave_mod, duration_mod = match.groups()
    degree = int(degree)
    
    # 计算基础音高
    base_pitch = KEY_TO_BASE[key]
    semitone = SCALE_DEGREES[degree - 1]
    
    # 处理升降号
    if accidental == '#':
        semitone += 1
    elif accidental == 'b':
        semitone -= 1
    
    # 处理八度偏移
    octave = 0
    for c in octave_mod:
        octave += 1 if c == '^' else -1
    
    # 计算最终音高
    midi_pitch = base_pitch + semitone + (octave * 12)
    if not 0 <= midi_pitch <= 127:
        raise ValueError(f"音高超出范围(0-127): {midi_pitch}")
    
    # 计算时值
    duration = 1.0
    for c in duration_mod:
        duration *= 2 if c == '-' else 1.5
    
    return midi_pitch, duration

def create_midi(global_meta, tracks, output_path):
    """生成多轨MIDI文件"""
    mid = MidiFile(ticks_per_beat=global_meta['ticks_per_beat'])
    
    for track_data in tracks:
        track = MidiTrack()
        mid.tracks.append(track)
        
        # 添加元数据
        track.append(MetaMessage('set_tempo', 
                               tempo=track_data['metadata']['tempo'], 
                               time=0))
        track.append(MetaMessage('time_signature',
                               numerator=track_data['metadata']['time_signature'][0],
                               denominator=track_data['metadata']['time_signature'][1],
                               time=0))
        track.append(Message('program_change',
                           program=track_data['metadata']['instrument'],
                           time=0))

        events = []
        current_time = 0
        key = track_data['metadata']['key']
        
        for note_str in track_data['notes']:
            try:
                pitch, duration = parse_note(note_str, key)
            except Exception as e:
                raise ValueError(f"解析音符失败: {note_str} - {str(e)}")
            
            ticks = int(duration * global_meta['ticks_per_beat'])
            
            if pitch is None:  # 休止符
                current_time += ticks
            else:
                events.append(('note_on', pitch, current_time))
                events.append(('note_off', pitch, current_time + ticks))
                current_time += ticks
        
        # 排序并写入事件
        events.sort(key=lambda x: x[2])
        last_time = 0
        for event in events:
            delta = event[2] - last_time
            track.append(Message(event[0], note=event[1], velocity=64, time=delta))
            last_time = event[2]
        
        # 添加轨道结束标记
        if current_time > last_time:
            track.append(MetaMessage('end_of_track', time=current_time - last_time))
        else:
            track.append(MetaMessage('end_of_track', time=0))
    
    mid.save(output_path)

def main_cli():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='简谱转MIDI命令行版 v1.0',
        epilog='示例: python nmn2midi_core.py input.txt -o output.mid')
    parser.add_argument('input', help='输入文本文件路径')
    parser.add_argument('-o', '--output', default='output.mid', help='输出MIDI文件路径')
    
    args = parser.parse_args()
    
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
        
        global_meta, tracks, warnings = parse_input(content)
        create_midi(global_meta, tracks, args.output)
        
        print(f"成功生成: {args.output}")
        if warnings:
            print("\n警告:")
            for warn in warnings:
                print(f"  {warn}")
                
    except Exception as e:
        print(f"\n错误: {str(e)}")
        exit(1)

if __name__ == '__main__':
    main_cli()