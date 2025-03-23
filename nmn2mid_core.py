import re
import mido
import re
import argparse
import os
import sys
from typing import Dict, List, Tuple, Optional
from mido import MidiFile, MidiTrack, Message, MetaMessage
from fractions import Fraction

# 基础音高配置（扩展支持小写和全称调号）
KEY_ROOT_TO_BASE = {
    'C': 60, 'C#': 61, 'Db': 61, 'D': 62, 'D#': 63, 'Eb': 63,
    'E': 64, 'F': 65, 'F#': 66, 'Gb': 66, 'G': 67, 'G#': 68,
    'Ab': 68, 'A': 69, 'A#': 70, 'Bb': 70, 'B': 71
}
SCALE_PATTERNS = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10]
}
DEFAULT_TICKS_PER_BEAT = 480
DEFAULT_INSTRUMENT = 0
DEFAULT_TEMPO = mido.bpm2tempo(120)
DEFAULT_TIME_SIGNATURE = (4, 4)
DEFAULT_KEY = ('C', 'major')

def parse_key(value: str) -> Tuple[str, str]:
    """统一解析调号格式（支持大小写和多种模式写法）"""
    match = re.match(
        r'^([A-Ga-g](?:#|b)?)\s*((?:m|min|minor|maj|major)?)$',
        value.strip(),
        re.IGNORECASE
    )
    if not match:
        raise ValueError(f"无效调号格式: {value}")

    root = match.group(1).upper()
    mode_str = (match.group(2) or '').lower()

    # 模式匹配
    if mode_str in ('m', 'min', 'minor'):
        mode = 'minor'
    elif mode_str in ('maj', 'major', ''):
        mode = 'major'
    else:
        raise ValueError(f"未知调式: {mode_str}")

    if root not in KEY_ROOT_TO_BASE:
        raise ValueError(f"无效根音: {root}")

    return root, mode

def parse_global_metadata(line: str, line_num: int, 
                        global_defaults: Dict, warnings: List[str]) -> None:
    """解析全局元数据行（增强错误处理）"""
    try:
        # 分离注释并去除空白
        key_part = line[1:].split('#', 1)[0].strip()
        if '=' not in key_part:
            raise ValueError("缺少等号分隔符")
            
        key, value = map(str.strip, key_part.split('=', 1))
        key = key.lower().replace('global_', '')
        
        if key == 'tempo':
            if not value.isdigit():
                raise ValueError("速度必须是整数")
            global_defaults['tempo'] = mido.bpm2tempo(int(value))
        elif key == 'time_signature':
            if '/' not in value:
                raise ValueError("拍号格式应为 分子/分母")
            numerator, denominator = map(str.strip, value.split('/', 1))
            if not numerator.isdigit() or not denominator.isdigit():
                raise ValueError("分子分母必须是整数")
            global_defaults['time_signature'] = (int(numerator), int(denominator))
        elif key == 'key':
            root, mode = parse_key(value)
            global_defaults.update({
                'key': (root, mode),
                'key_root': root,
                'key_mode': mode
            })
        elif key == 'instrument':
            if not value.isdigit() or not 0 <= int(value) <= 127:
                raise ValueError("乐器编号必须是0-127的整数")
            global_defaults['instrument'] = int(value)
        else:
            warnings.append(f"第{line_num}行: 未知的全局参数 '{key}'")
    except Exception as e:
        raise ValueError(f"第{line_num}行全局参数错误: {str(e)}")

def parse_track_metadata(line: str, line_num: int,
                       current_track: Dict, warnings: List[str]) -> None:
    """解析轨道元数据（复用调号解析逻辑）"""
    try:
        key_part = line[1:].split('#', 1)[0].strip()
        if '=' not in key_part:
            raise ValueError("缺少等号分隔符")
            
        key, value = map(str.strip, key_part.split('=', 1))
        key = key.lower()
        
        if key == 'tempo':
            warnings.append(f"第{line_num}行: 轨道级tempo参数已禁用")
        elif key == 'time_signature':
            warnings.append(f"第{line_num}行: 轨道级拍号参数已禁用")
        elif key == 'key':
            root, mode = parse_key(value)
            current_track['metadata'].update({
                'key': (root, mode),
                'key_root': root,
                'key_mode': mode
            })
            current_track['provided']['key'] = True
        elif key == 'instrument':
            if not value.isdigit() or not 0 <= int(value) <= 127:
                raise ValueError("乐器编号必须是0-127的整数")
            current_track['metadata']['instrument'] = int(value)
            current_track['provided']['instrument'] = True
        else:
            warnings.append(f"第{line_num}行: 未知的轨道参数 '{key}'")
    except Exception as e:
        raise ValueError(f"第{line_num}行轨道参数错误: {str(e)}")

def parse_input(content: str) -> Tuple[Dict, List[Dict], List[str]]:
    """解析输入内容（增加行号追踪）"""
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
    
    for line_num, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.split('#', 1)[0].strip()  # 保留原始行用于错误报告
        if not line:
            continue
        
        try:
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
                        'notes': [],
                        'source_lines': []  # 记录原始音符行
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
                    current_track['notes'].extend(line.split())
                    current_track['source_lines'].append((line_num, raw_line))
        except Exception as e:
            raise ValueError(f"第{line_num}行解析错误: {str(e)}\n原始行: {raw_line}")
    
    # 后处理验证
    for track_idx, track in enumerate(tracks, 1):
        if not track['notes']:
            warnings.append(f"轨道 {track_idx}: 空轨道（无音符数据）")
        
        for param in ['key', 'instrument']:
            if not track['provided'][param]:
                desc = track['metadata'][param]
                if param == 'key':
                    desc = f"{desc[0]}{'小调' if desc[1] == 'minor' else '大调'}"
                warnings.append(f"轨道 {track_idx}: 使用全局{param} ({desc})")
    
    return global_defaults, tracks, warnings

def parse_note(note_str: str, key_root: str, key_mode: str) -> Tuple[Optional[int], Fraction]:
    """解析音符（增强格式验证）"""
    if note_str.startswith('0'):
        match = re.fullmatch(r'0([.-]*)', note_str)
        if not match:
            raise ValueError(f"无效休止符格式: {note_str}")
        mods = match.group(1)
        return None, _calculate_duration(mods)
    
    match = re.fullmatch(r'^([#b]?)([1-7])([_^]*)([.-]*)$', note_str)
    if not match:
        raise ValueError(f"无效音符格式: {note_str}")
    
    accidental, degree_str, octave_mod, duration_mod = match.groups()
    
    # 验证升降号
    if accidental not in ('', '#', 'b'):
        raise ValueError(f"无效的升降号: {accidental}")
    
    # 计算音级
    try:
        degree = int(degree_str)
    except ValueError:
        raise ValueError(f"无效音级: {degree_str}")
    if not 1 <= degree <= 7:
        raise ValueError(f"音级超出范围 (1-7): {degree}")
    
    # 计算音高
    base_pitch = KEY_ROOT_TO_BASE[key_root]
    scale = SCALE_PATTERNS[key_mode]
    semitone = scale[degree - 1] + _accidental_offset(accidental)
    
    # 计算八度移位
    octave = octave_mod.count('^') - octave_mod.count('_')
    midi_pitch = base_pitch + semitone + (octave * 12)
    if not 0 <= midi_pitch <= 127:
        raise ValueError(f"音高超出范围 (0-127): {midi_pitch}")
    
    return midi_pitch, _calculate_duration(duration_mod)

def _accidental_offset(accidental: str) -> int:
    """计算升降号偏移量"""
    return 1 if accidental == '#' else -1 if accidental == 'b' else 0

def _calculate_duration(mods: str) -> Fraction:
    """计算时值（精确分数计算）"""
    dashes = mods.count('-')
    dots = mods.count('.')
    
    # 基础时值
    duration = Fraction(1)
    
    # 连字符处理
    duration /= (2 ** dashes)
    
    # 附点处理
    for _ in range(dots):
        duration += duration / 2
    
    return duration

def create_track_events(track_data: Dict, ticks_per_beat: int) -> List[Tuple]:
    """生成轨道事件（带错误上下文）"""
    events = []
    current_time = 0
    key_root = track_data['metadata']['key_root']
    key_mode = track_data['metadata']['key_mode']
    errors = []
    
    for note_str in track_data['notes']:
        try:
            pitch, duration = parse_note(note_str, key_root, key_mode)
            ticks = int(round(duration * ticks_per_beat))
            
            if ticks <= 0:
                raise ValueError("时值过小")
                
            if pitch is None:  # 休止符
                current_time += ticks
            else:
                events.append(('note_on', pitch, current_time))
                events.append(('note_off', pitch, current_time + ticks))
                current_time += ticks
        except Exception as e:
            # 查找原始行号
            line_nums = [ln for ln, l in track_data['source_lines'] if note_str in l.split()]
            err_msg = f"'{note_str}'"
            if line_nums:
                err_msg += f" (出现在第{min(line_nums)}行)"
            errors.append(f"{err_msg}: {str(e)}")
    
    if errors:
        raise ValueError("音符错误:\n" + "\n".join(f"  • {e}" for e in errors))
    
    # 按时间排序并计算delta时间
    events.sort(key=lambda x: x[2])
    return events

def create_midi(global_meta: Dict, tracks: List[Dict], output_path: str) -> None:
    """生成MIDI文件（增强鲁棒性）"""
    if not tracks:
        raise ValueError("无有效轨道数据")
    
    try:
        mid = MidiFile(ticks_per_beat=global_meta['ticks_per_beat'])
        
        # 全局轨道
        global_track = MidiTrack()
        mid.tracks.append(global_track)
        global_track.append(MetaMessage('set_tempo',
                                      tempo=global_meta['tempo'],
                                      time=0))
        global_track.append(MetaMessage('time_signature',
                                      numerator=global_meta['time_signature'][0],
                                      denominator=global_meta['time_signature'][1],
                                      time=0))
        
        # 各音乐轨道
        for track_idx, track_data in enumerate(tracks, 1):
            track = MidiTrack()
            mid.tracks.append(track)
            
            # 设置乐器
            track.append(Message('program_change',
                              program=track_data['metadata']['instrument'],
                              time=0))
            
            try:
                events = create_track_events(track_data, global_meta['ticks_per_beat'])
            except ValueError as e:
                raise ValueError(f"轨道 {track_idx} 错误:\n{str(e)}")
            
            # 生成MIDI消息
            last_time = 0
            for event in events:
                delta = event[2] - last_time
                track.append(Message(event[0], note=event[1], velocity=64, time=delta))
                last_time = event[2]
            
            # 轨道结束
            end_time = events[-1][2] if events else 0
            track.append(MetaMessage('end_of_track', time=max(0, end_time - last_time)))
        
        # 保存前验证
        if len(mid.tracks) < 2:
            raise ValueError("无有效音乐轨道")
            
        mid.save(output_path)
    except (IOError, OSError) as e:
        raise ValueError(f"文件保存失败: {str(e)}")

def main_cli():
    """命令行接口（增强错误处理）"""
    parser = argparse.ArgumentParser(
        description='简谱转MIDI转换器 v2.0',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""输入文件格式示例：
@global_tempo = 120
@global_time_signature = 4/4
@global_key = C

[track]
1 2 3 4 | 5 6 7 1^

支持特性：
• 多轨道支持
• 复杂节奏型（附点、连音线）
• 全调号支持（含大小调）
• 行内注释（#符号）"""
    )
    parser.add_argument('input', help='输入文本文件路径')
    parser.add_argument('-o', '--output', default='output.mid',
                      help='输出MIDI文件路径（默认：output.mid）')
    parser.add_argument('-v', '--verbose', action='store_true',
                      help='显示详细解析信息')
    
    args = parser.parse_args()
    
    try:
        # 输入验证
        if not os.path.exists(args.input):
            raise ValueError(f"输入文件不存在: {args.input}")
        if os.path.isdir(args.input):
            raise ValueError(f"输入路径是目录: {args.input}")
            
        # 读取文件
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 解析并生成
        global_meta, tracks, warnings = parse_input(content)
        create_midi(global_meta, tracks, args.output)
        
        # 输出结果
        print(f"✓ 成功生成: {os.path.abspath(args.output)}")
        print(f"• 轨道数: {len(tracks)}")
        print(f"• 速度: {mido.tempo2bpm(global_meta['tempo']):.0f} BPM")
        print(f"• 拍号: {global_meta['time_signature'][0]}/{global_meta['time_signature'][1]}")
        print(f"• 调号: {global_meta['key_root']} {global_meta['key_mode']}")
        
        if warnings or args.verbose:
            print("\n详细报告:")
            for warn in warnings:
                print(f"  ⚠ {warn}")
                
    except Exception as e:
        print(f"\n✗ 错误: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main_cli()