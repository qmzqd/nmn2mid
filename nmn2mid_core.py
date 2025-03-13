# File 1: nmn2midi_core.py
import mido
import re
import copy
import argparse
from mido import MidiFile, MidiTrack, Message, MetaMessage

# 基础音高配置（扩展支持小调）
KEY_ROOT_TO_BASE = {
    'C': 60, 'C#': 61, 'Db': 61, 'D': 62, 'D#': 63, 'Eb': 63,
    'E': 64, 'F': 65, 'F#': 66, 'Gb': 66, 'G': 67, 'G#': 68,
    'Ab': 68, 'A': 69, 'A#': 70, 'Bb': 70, 'B': 71
}
SCALE_PATTERNS = {
    'major': [0, 2, 4, 5, 7, 9, 11],    # 大调音阶
    'minor': [0, 2, 3, 5, 7, 8, 10]     # 自然小调音阶
}
DEFAULT_TICKS_PER_BEAT = 480
DEFAULT_INSTRUMENT = 0
DEFAULT_TEMPO = mido.bpm2tempo(120)
DEFAULT_TIME_SIGNATURE = (4, 4)
DEFAULT_KEY = ('C', 'major')

def parse_global_metadata(line, line_num, global_defaults, warnings):
    """解析全局元数据行（支持行内注释）"""
    key_part = line[1:].split('#')[0].strip()
    key, value = key_part.split('=', 1)
    key = key.lower().replace('global_', '')
    
    try:
        if key == 'tempo':
            global_defaults['tempo'] = mido.bpm2tempo(int(value))
        elif key == 'time_signature':
            numerator, denominator = map(int, value.split('/'))
            global_defaults['time_signature'] = (numerator, denominator)
        elif key == 'key':
            # 解析调号（支持大小调，如C、Am、G#m等）
            match = re.match(r'^([A-Ga-g](?:#|b)?)(m|min|minor)?$', 
                           value.strip(), re.IGNORECASE)
            if not match:
                raise ValueError(f"无效调号格式: {value}")
            
            root = match.group(1).upper()
            mode = 'minor' if match.group(2) else 'major'
            
            if root not in KEY_ROOT_TO_BASE:
                raise ValueError(f"无效根音: {root}")
            
            global_defaults['key'] = (root, mode)
            global_defaults['key_root'] = root
            global_defaults['key_mode'] = mode
        elif key == 'instrument':
            program = int(value)
            if not 0 <= program <= 127:
                raise ValueError("乐器编号超出范围 (0-127)")
            global_defaults['instrument'] = program
        else:
            warnings.append(f"第{line_num}行: 未知的全局参数 '{key}'")
    except Exception as e:
        raise ValueError(f"第{line_num}行全局参数错误: {str(e)}")

def parse_track_metadata(line, line_num, current_track, warnings):
    """解析轨道元数据行（支持行内注释）"""
    key_part = line[1:].split('#')[0].strip()
    key, value = key_part.split('=', 1)
    key = key.lower()
    
    try:
        if key == 'tempo':
            warnings.append(f"第{line_num}行: 轨道tempo参数已被弃用，请使用全局设置")
        elif key == 'time_signature':
            warnings.append(f"第{line_num}行: 轨道time_signature参数已被弃用，请使用全局设置")
        elif key == 'key':
            # 解析调号（支持大小调）
            match = re.match(r'^([A-Ga-g](?:#|b)?)(m|min|minor)?$', 
                           value.strip(), re.IGNORECASE)
            if not match:
                raise ValueError(f"无效调号格式: {value}")
            
            root = match.group(1).upper()
            mode = 'minor' if match.group(2) else 'major'
            
            if root not in KEY_ROOT_TO_BASE:
                raise ValueError(f"无效根音: {root}")
            
            current_track['metadata']['key'] = (root, mode)
            current_track['metadata']['key_root'] = root
            current_track['metadata']['key_mode'] = mode
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

def parse_input(content):
    """解析输入内容并返回全局元数据、轨道列表和警告信息"""
    global_defaults = {
        'tempo': DEFAULT_TEMPO,
        'time_signature': DEFAULT_TIME_SIGNATURE,
        'key': DEFAULT_KEY,
        'key_root': DEFAULT_KEY[0],
        'key_mode': DEFAULT_KEY[1],
        'instrument': DEFAULT_INSTRUMENT,
        'ticks_per_beat': DEFAULT_TICKS_PER_BEAT
    }
    tracks = []
    current_track = None
    in_global_section = True
    warnings = []
    
    lines = content.split('\n')
    for line_num, line in enumerate(lines, 1):
        # 移除整行注释和空白
        line = line.split('#')[0].strip()
        if not line:
            continue
        
        if line.startswith('['):
            if line.lower().startswith('[track'):
                current_track = {
                    'metadata': {
                        'tempo': global_defaults['tempo'],
                        'time_signature': global_defaults['time_signature'],
                        'key': (global_defaults['key_root'], 
                               global_defaults['key_mode']),
                        'key_root': global_defaults['key_root'],
                        'key_mode': global_defaults['key_mode'],
                        'instrument': global_defaults['instrument'],
                        'ticks_per_beat': global_defaults['ticks_per_beat']
                    },
                    'provided': {'key': False, 'instrument': False},
                    'notes': []
                }
                in_global_section = False
                tracks.append(current_track)
            continue
        
        if in_global_section and line.startswith('@'):
            parse_global_metadata(line, line_num, global_defaults, warnings)
        elif current_track is not None:
            if line.startswith('@'):
                parse_track_metadata(line, line_num, current_track, warnings)
            else:
                # 解析音符行（支持行内注释）
                current_track['notes'].extend(line.split())
    
    # 生成警告信息
    for track_idx, track in enumerate(tracks, 1):
        for param in ['key', 'instrument']:
            if not track['provided'][param]:
                if param == 'key':
                    root = track['metadata']['key_root']
                    mode = track['metadata']['key_mode']
                    desc = f"{root}{'小调' if mode == 'minor' else '大调'}"
                else:
                    desc = str(track['metadata'][param])
                warnings.append(
                    f"轨道 {track_idx}: 使用全局{param} ({desc})")
    
    return global_defaults, tracks, warnings

def parse_note(note_str, key_root, key_mode):
    """解析单个音符字符串（支持升降号、八度移位和复杂时值）"""
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
    base_pitch = KEY_ROOT_TO_BASE[key_root]
    scale = SCALE_PATTERNS[key_mode]
    if degree < 1 or degree > 7:
        raise ValueError(f"无效音级 (1-7): {degree}")
    semitone = scale[degree - 1]
    
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

def create_track_events(track_data, ticks_per_beat):
    """生成轨道事件列表（优化时序计算）"""
    events = []
    current_time = 0
    key_root = track_data['metadata']['key_root']
    key_mode = track_data['metadata']['key_mode']
    
    for note_str in track_data['notes']:
        try:
            pitch, duration = parse_note(note_str, key_root, key_mode)
            ticks = int(duration * ticks_per_beat)

            if pitch is None:  # 休止符
                current_time += ticks
            else:
                events.append(('note_on', pitch, current_time))
                events.append(('note_off', pitch, current_time + ticks))
                current_time += ticks
        except Exception as e:
            print(f"Error parsing note: {note_str} with error {str(e)}")
    
    # 排序事件并计算delta时间
    events.sort(key=lambda x: x[2])
    return events

def create_midi(global_meta, tracks, output_path):
    """生成多轨MIDI文件（增强元数据支持）"""
    mid = MidiFile(ticks_per_beat=global_meta['ticks_per_beat'])
    
    # 创建全局控制轨道
    global_track = MidiTrack()
    mid.tracks.append(global_track)
    global_track.append(MetaMessage('set_tempo', 
                                  tempo=global_meta['tempo'], 
                                  time=0))
    global_track.append(MetaMessage('time_signature',
                                  numerator=global_meta['time_signature'][0],
                                  denominator=global_meta['time_signature'][1],
                                  time=0))
    
    # 创建各音乐轨道
    for track_data in tracks:
        track = MidiTrack()
        mid.tracks.append(track)
        
        # 设置乐器
        track.append(Message('program_change',
                          program=track_data['metadata']['instrument'],
                          time=0))
        
        # 生成事件并写入轨道
        events = create_track_events(track_data, global_meta['ticks_per_beat'])
        last_time = 0
        for event in events:
            delta = event[2] - last_time
            track.append(Message(event[0], note=event[1], velocity=64, time=delta))
            last_time = event[2]
        
        # 添加轨道结束标记
        end_time = events[-1][2] if events else 0
        track.append(MetaMessage('end_of_track', time=max(0, end_time - last_time)))

    mid.save(output_path)

def main_cli():
    """命令行入口（改进帮助信息）"""
    parser = argparse.ArgumentParser(
        description='简谱转MIDI命令行版 v1.0',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog='示例：\n'
               '  python nmn2midi_core.py input.txt -o output.mid\n\n'
               '支持特性：\n'
               '- 全调号支持（包括大调和小调，如C、Am、F#m等）\n'
               '- 行内注释（使用#符号）\n'
               '- 复杂节奏型（附点、连音线）\n'
               '- 多轨道支持')
    parser.add_argument('input', help='输入文本文件路径')
    parser.add_argument('-o', '--output', default='output.mid', 
                       help='输出MIDI文件路径（默认：output.mid）')
    
    args = parser.parse_args()
    
    try:
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
        
        global_meta, tracks, warnings = parse_input(content)
        create_midi(global_meta, tracks, args.output)
        
        print(f"成功生成: {args.output}")
        if warnings:
            print("\n警告：")
            for warn in warnings:
                print(f"  {warn}")
                
    except Exception as e:
        print(f"\n错误: {str(e)}")
        exit(1)

if __name__ == '__main__':
    main_cli()
