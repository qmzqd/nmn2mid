import re
import mido
import argparse
import os
import sys
from typing import Dict, List, Tuple, Optional
from mido import MidiFile, MidiTrack, Message, MetaMessage
from fractions import Fraction

# 基础配置
KEY_ROOT_TO_BASE = {
    'C': 60, 'C#': 61, 'Db': 61, 'D': 62, 'D#': 63, 'Eb': 63,
    'E': 64, 'F': 65, 'F#': 66, 'Gb': 66, 'G': 67, 'G#': 68,
    'Ab': 68, 'A': 69, 'A#': 70, 'Bb': 70, 'B': 71
}
SCALE_PATTERNS = {
    'major': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'drum': []
}
DEFAULT_TICKS_PER_BEAT = 480
DEFAULT_INSTRUMENT = 0
DEFAULT_TEMPO = mido.bpm2tempo(120)
DEFAULT_TIME_SIGNATURE = (4, 4)
DEFAULT_KEY = ('C', 'major', 0)

def parse_key(value: str) -> Tuple[str, str, int]:
    """解析调号（增强格式兼容性）"""
    # 鼓组调号处理 (如C5)
    drum_match = re.match(r'^\s*([A-Ga-g])(\d+)\s*$', value, re.IGNORECASE)
    if drum_match:
        root = drum_match.group(1).upper()
        return root, 'drum', int(drum_match.group(2)) - (5 if root == 'C' else 4)

    # 常规调号处理 (如C+1)
    match = re.match(
        r'^\s*([A-Ga-g](?:#|b)?)\s*((?:m|min|minor|maj|major)?)\s*([+-]\d+)?\s*$',
        value,
        re.IGNORECASE
    )
    if not match:
        raise ValueError(f"无效调号格式: {value}")

    root = match.group(1).upper()
    mode = 'minor' if any(x in (match.group(2) or '').lower() for x in ['m', 'min']) else 'major'
    octave = int(match.group(3) or 0) if match.group(3) else 0

    if root not in KEY_ROOT_TO_BASE:
        raise ValueError(f"无效根音: {root}")

    return root, mode, octave

def parse_note(note_str: str, key_root: str, key_mode: str, key_octave: int) -> Tuple[Optional[int], Fraction, Optional[str]]:
    """解析音符（增强容错处理）"""
    # 预处理：移除非法字符并标准化
    note_str = re.sub(r'[|]', '', note_str).strip()  # 移除小节分隔符
    
    # 纯歌词处理（允许空歌词）
    if note_str.startswith('"'):
        end_quote = note_str.find('"', 1)
        if end_quote == -1:
            lyric = note_str[1:]
        else:
            lyric = note_str[1:end_quote]
        return None, Fraction(1, 64), lyric.strip() or None
    
    # 分割歌词和音符部分
    note_part = lyric_part = ""
    if '"' in note_str:
        note_part, _, lyric_part = note_str.partition('"')
        lyric_part = lyric_part.rstrip('"')  # 移除右引号
    else:
        note_part = note_str
    
    note_part = note_part.strip()
    lyric = lyric_part.strip() if lyric_part else None

    # 休止符处理（支持0+格式）
    if note_part.startswith('0'):
        mods = note_part[1:].replace('0', '')  # 支持多个0
        return None, _calculate_duration(mods), lyric
    
    # 鼓组处理
    if key_mode == 'drum':
        if not note_part:
            raise ValueError("鼓组音符不能为空")
        try:
            return mido.note_name_to_number(note_part.upper()), _calculate_duration(''), lyric
        except ValueError:
            raise ValueError(f"无效鼓组音符: {note_part}")
    
    # 常规音符解析
    match = re.match(
        r'^([#b]?)\s*([1-7])\s*([_^]*)\s*([.-]*)$',
        note_part
    )
    if not match:
        raise ValueError(f"无效音符格式: {note_part}")

    accidental, degree_str, octave_mod, duration_mod = match.groups()
    
    # 音高计算
    try:
        degree = int(degree_str)
        if not 1 <= degree <= 7:
            raise ValueError
    except:
        raise ValueError(f"音级必须为1-7: {degree_str}")
    
    try:
        base_pitch = KEY_ROOT_TO_BASE[key_root] + key_octave * 12
        semitone = SCALE_PATTERNS[key_mode][degree-1] + (1 if accidental == '#' else -1 if accidental == 'b' else 0)
        octave = octave_mod.count('^') - octave_mod.count('_')
        midi_pitch = base_pitch + semitone + octave * 12
        midi_pitch = max(0, min(127, midi_pitch))  # 强制限制范围
    except IndexError:
        raise ValueError(f"无效音阶模式: {key_mode}")

    return midi_pitch, _calculate_duration(duration_mod), lyric

def _calculate_duration(mods: str) -> Fraction:
    """时值计算（带保护机制）"""
    dashes = min(mods.count('-'), 3)  # 最多3个连字符（全音符×8）
    dots = min(mods.count('.'), 2)    # 最多2个附点
    
    duration = Fraction(1)
    duration /= (2 ** dashes)
    
    for _ in range(dots):
        duration += duration / 2
    
    # 确保最小单位为1/64音符
    return max(duration, Fraction(1, 64))

def parse_global_metadata(line: str, line_num: int, 
                        global_defaults: Dict, warnings: List[str]) -> None:
    """解析全局元数据行"""
    try:
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
            root, mode, octave = parse_key(value)
            global_defaults.update({
                'key': (root, mode, octave),
                'key_root': root,
                'key_mode': mode,
                'key_octave': octave
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
    """解析轨道元数据"""
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
            root, mode, octave = parse_key(value)
            current_track['metadata'].update({
                'key': (root, mode, octave),
                'key_root': root,
                'key_mode': mode,
                'key_octave': octave
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
    """解析输入内容"""
    global_defaults = {
        'tempo': DEFAULT_TEMPO,
        'time_signature': DEFAULT_TIME_SIGNATURE,
        'key': DEFAULT_KEY,
        'key_root': DEFAULT_KEY[0],
        'key_mode': DEFAULT_KEY[1],
        'key_octave': DEFAULT_KEY[2],
        'instrument': DEFAULT_INSTRUMENT,
        'ticks_per_beat': DEFAULT_TICKS_PER_BEAT
    }
    tracks = []
    current_track = None
    in_global_section = True
    warnings = []
    
    for line_num, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.split('#', 1)[0].strip()
        if not line:
            continue
        
        try:
            if line.startswith('['):
                if line.lower().startswith('[track'):
                    current_track = {
                        'metadata': {
                            'tempo': global_defaults['tempo'],
                            'time_signature': global_defaults['time_signature'],
                            'key': global_defaults['key'],
                            'key_root': global_defaults['key_root'],
                            'key_mode': global_defaults['key_mode'],
                            'key_octave': global_defaults['key_octave'],
                            'instrument': global_defaults['instrument'],
                            'ticks_per_beat': global_defaults['ticks_per_beat']
                        },
                        'provided': {'key': False, 'instrument': False},
                        'notes': [],
                        'source_lines': []
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
                    desc = f"{desc[0]} {desc[1]}"
                warnings.append(f"轨道 {track_idx}: 使用全局{param} ({desc})")
    
    return global_defaults, tracks, warnings

def parse_note(note_str: str, key_root: str, key_mode: str, key_octave: int) -> Tuple[Optional[int], Fraction, Optional[str]]:
    """解析音符（支持鼓组专用处理）"""
    # 处理纯歌词的情况
    lyric_match = re.fullmatch(r'^\s*"(.*?)"\s*$', note_str)
    if lyric_match:
        return None, Fraction(0), lyric_match.group(1)
    
    # 处理休止符带歌词的情况
    if note_str.startswith('0'):
        match = re.fullmatch(r'0([.-]*)(?:\s*"(.*?)")?$', note_str)
        if not match:
            raise ValueError(f"无效休止符格式: {note_str}")
        mods, lyric = match.groups()
        return None, _calculate_duration(mods), lyric
    
    # 鼓组专用处理
    if key_mode == 'drum':
        match = re.fullmatch(r'^([A-Ga-g]\d+)([.-]*)(?:\s*"(.*?)")?$', note_str, re.IGNORECASE)
        if match:
            note_name, duration_mod, lyric = match.groups()
            try:
                midi_pitch = mido.note_name_to_number(note_name.upper())
                return midi_pitch, _calculate_duration(duration_mod), lyric
            except ValueError:
                raise ValueError(f"无效鼓组音符: {note_name}")
        else:
            raise ValueError(f"鼓组轨道需使用标准音符命名 (如C5, D#3): {note_str}")

    # 常规音符处理
    match = re.fullmatch(r'^([#b]?)([1-7])([_^]*)([.-]*)(?:\s*"(.*?)")?$', note_str)
    if not match:
        raise ValueError(f"无效音符格式: {note_str}")
    
    accidental, degree_str, octave_mod, duration_mod, lyric = match.groups()
    
    if accidental not in ('', '#', 'b'):
        raise ValueError(f"无效的升降号: {accidental}")
    
    try:
        degree = int(degree_str)
    except ValueError:
        raise ValueError(f"无效音级: {degree_str}")
    if not 1 <= degree <= 7:
        raise ValueError(f"音级超出范围 (1-7): {degree}")
    
    base_pitch = KEY_ROOT_TO_BASE[key_root] + key_octave * 12
    scale = SCALE_PATTERNS[key_mode]
    semitone = scale[degree - 1] + _accidental_offset(accidental)
    
    octave = octave_mod.count('^') - octave_mod.count('_')
    midi_pitch = base_pitch + semitone + (octave * 12)
    if not 0 <= midi_pitch <= 127:
        raise ValueError(f"音高超出范围 (0-127): {midi_pitch}")
    
    return midi_pitch, _calculate_duration(duration_mod), lyric

def _accidental_offset(accidental: str) -> int:
    """计算升降号偏移量"""
    return 1 if accidental == '#' else -1 if accidental == 'b' else 0

def _calculate_duration(mods: str) -> Fraction:
    """计算时值（精确分数计算）"""
    dashes = mods.count('-')
    dots = mods.count('.')
    
    duration = Fraction(1)
    duration /= (2 ** dashes)
    
    for _ in range(dots):
        duration += duration / 2
    
    return duration

def create_track_events(track_data: Dict, ticks_per_beat: int) -> List[Tuple]:
    """生成轨道事件"""
    events = []
    current_time = 0
    key_root = track_data['metadata']['key_root']
    key_mode = track_data['metadata']['key_mode']
    key_octave = track_data['metadata']['key_octave']
    errors = []
    
    for note_str in track_data['notes']:
        try:
            pitch, duration, lyric = parse_note(note_str, key_root, key_mode, key_octave)
            ticks = int(round(duration * ticks_per_beat))
            
            if ticks <= 0:
                raise ValueError("时值过小")
                
            if pitch is None:  # 休止符或纯歌词
                if lyric:
                    events.append(('lyric', lyric, current_time))
                current_time += ticks
            else:
                events.append(('note_on', pitch, current_time))
                events.append(('note_off', pitch, current_time + ticks))
                if lyric:
                    events.append(('lyric', lyric, current_time))
                current_time += ticks
        except Exception as e:
            line_nums = [ln for ln, l in track_data['source_lines'] if note_str in l.split()]
            err_msg = f"'{note_str}'"
            if line_nums:
                err_msg += f" (出现在第{min(line_nums)}行)"
            errors.append(f"{err_msg}: {str(e)}")
    
    if errors:
        raise ValueError("音符错误:\n" + "\n".join(f"  • {e}" for e in errors))
    
    events.sort(key=lambda x: x[2])
    return events

def create_midi(global_meta: Dict, tracks: List[Dict], output_path: str) -> None:
    """生成MIDI文件"""
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
            
            track.append(Message('program_change',
                              program=track_data['metadata']['instrument'],
                              time=0))
            
            try:
                events = create_track_events(track_data, global_meta['ticks_per_beat'])
            except ValueError as e:
                raise ValueError(f"轨道 {track_idx} 错误:\n{str(e)}")
            
            last_time = 0
            for event in events:
                delta = event[2] - last_time
                if event[0] in ('note_on', 'note_off'):
                    track.append(Message(event[0], note=event[1], velocity=64, time=delta))
                elif event[0] == 'lyric':
                    track.append(MetaMessage('text', text=event[1], time=delta))
                last_time = event[2]
            
            end_time = events[-1][2] if events else 0
            track.append(MetaMessage('end_of_track', time=max(0, end_time - last_time)))
        
        mid.save(output_path)
    except (IOError, OSError) as e:
        raise ValueError(f"文件保存失败: {str(e)}")

def main_cli():
    """命令行接口"""
    parser = argparse.ArgumentParser(
        description='简谱转MIDI转换器 v2.1',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""输入文件示例：
@global_tempo=120
@global_key=C

[track]
@instrument=118  # 鼓组
@key=C5
C5 "Kick" D5 "Snare"

[track]
@instrument=0    # 钢琴
1 3 5 | 2 4 6"""
    )
    parser.add_argument('input', help='输入文本文件路径')
    parser.add_argument('-o', '--output', default='output.mid',
                      help='输出MIDI文件路径（默认：output.mid）')
    parser.add_argument('-v', '--verbose', action='store_true',
                      help='显示详细解析信息')
    
    args = parser.parse_args()
    
    try:
        if not os.path.exists(args.input):
            raise ValueError(f"输入文件不存在: {args.input}")
        if os.path.isdir(args.input):
            raise ValueError(f"输入路径是目录: {args.input}")
            
        with open(args.input, 'r', encoding='utf-8') as f:
            content = f.read()
        
        global_meta, tracks, warnings = parse_input(content)
        create_midi(global_meta, tracks, args.output)
        
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