#!/usr/bin/env python3
"""Import Chiikawa character skins from Yaha-Pet assets into frontends/skins/."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
YAHA_ASSETS = ROOT / '.tmp_chiikawa' / 'Yaha-Pet' / 'assets'
OUT_DIR = ROOT / 'frontends' / 'skins'
DISPLAY_HEIGHT = 128
MAX_SOURCE_DIM = 256

# Only use loop-friendly clips: static/idle poses, or contiguous walk-cycle frames.
# Avoid spawn (intro) and jump (one-shot) animations for looping states.
CHAR_PLANS = {
    'chiikawa': {
        'name': 'Chiikawa',
        'description': '吉伊卡哇',
        'states': {
            'idle': {'kind': 'static', 'file': 'happy.png', 'hold_frames': 4, 'fps': 3},
            'walk': {'kind': 'animation', 'name': 'walkleft', 'start': 0, 'max_frames': 10, 'fps': 6},
            'run': {'kind': 'animation', 'name': 'walkleft', 'start': 0, 'max_frames': 8, 'fps': 10},
            'sprint': {'kind': 'animation', 'name': 'walkleft', 'start': 0, 'max_frames': 6, 'fps': 14},
        },
    },
    'hachiware': {
        'name': 'Hachiware',
        'description': '小八',
        'states': {
            'idle': {'kind': 'animation', 'name': 'walkleft', 'start': 0, 'max_frames': 6, 'fps': 3},
            'walk': {'kind': 'animation', 'name': 'walkleft', 'start': 0, 'max_frames': 10, 'fps': 6},
            'run': {'kind': 'animation', 'name': 'walkleft', 'start': 0, 'max_frames': 8, 'fps': 10},
            'sprint': {'kind': 'animation', 'name': 'walkleft', 'start': 0, 'max_frames': 6, 'fps': 16},
        },
    },
    'usagi': {
        'name': 'Usagi',
        'description': '乌萨奇',
        'states': {
            'idle': {'kind': 'animation', 'name': 'walkleft', 'start': 0, 'max_frames': 6, 'fps': 3},
            'walk': {'kind': 'animation', 'name': 'walkleft', 'start': 0, 'max_frames': 10, 'fps': 6},
            'run': {'kind': 'animation', 'name': 'walkleft', 'start': 0, 'max_frames': 8, 'fps': 10},
            'sprint': {'kind': 'animation', 'name': 'danceswirl', 'start': 0, 'max_frames': 10, 'fps': 12},
        },
    },
}


def frame_sort_key(path: Path) -> tuple:
    stem = path.stem
    digits = re.sub(r'\D', '', stem)
    return (int(digits) if digits else 0, stem)


def load_sprite(char_dir: Path, filename: str) -> Image.Image:
    path = char_dir / 'sprites' / filename
    if not path.is_file():
        raise FileNotFoundError(f'Missing sprite: {path}')
    return Image.open(path).convert('RGBA')


def load_animation_frames(char_dir: Path, anim_name: str) -> list[Image.Image]:
    anim_dir = char_dir / 'animations' / anim_name
    if not anim_dir.is_dir():
        raise FileNotFoundError(f'Missing animation folder: {anim_dir}')
    paths = sorted(anim_dir.glob('*.png'), key=frame_sort_key)
    return [Image.open(p).convert('RGBA') for p in paths]


def downscale_if_needed(img: Image.Image) -> Image.Image:
    longest = max(img.width, img.height)
    if longest <= MAX_SOURCE_DIM:
        return img
    scale = MAX_SOURCE_DIM / longest
    size = (max(1, int(round(img.width * scale))), max(1, int(round(img.height * scale))))
    return img.resize(size, Image.Resampling.LANCZOS)


def contiguous_indices(total: int, start: int, count: int) -> list[int]:
    if total <= 0:
        return []
    start = max(0, min(start, total - 1))
    end = min(start + count, total)
    indices = list(range(start, end))
    while len(indices) < count:
        indices.append(indices[-1])
    return indices


def normalize_frames(frames: list[Image.Image]) -> tuple[list[Image.Image], int, int]:
    if not frames:
        raise ValueError('No frames to normalize')
    max_w = max(img.width for img in frames)
    max_h = max(img.height for img in frames)
    normalized = []
    for img in frames:
        canvas = Image.new('RGBA', (max_w, max_h), (0, 0, 0, 0))
        x = (max_w - img.width) // 2
        y = max_h - img.height
        canvas.paste(img, (x, y), img)
        normalized.append(canvas)
    return normalized, max_w, max_h


def build_sprite_sheet(frames: list[Image.Image]) -> tuple[Image.Image, int, int]:
    normalized, fw, fh = normalize_frames(frames)
    sheet = Image.new('RGBA', (fw * len(normalized), fh), (0, 0, 0, 0))
    for i, frame in enumerate(normalized):
        sheet.paste(frame, (i * fw, 0), frame)
    return sheet, fw, fh


def display_size(frame_w: int, frame_h: int) -> dict[str, int]:
    if frame_h <= 0:
        return {'width': DISPLAY_HEIGHT, 'height': DISPLAY_HEIGHT}
    scale = DISPLAY_HEIGHT / frame_h
    return {
        'width': max(32, int(round(frame_w * scale))),
        'height': DISPLAY_HEIGHT,
    }


def collect_state_frames(char_dir: Path, spec: dict) -> list[Image.Image]:
    if spec['kind'] == 'static':
        base = downscale_if_needed(load_sprite(char_dir, spec['file']))
        return [base] * spec.get('hold_frames', 4)

    frames = load_animation_frames(char_dir, spec['name'])
    indices = contiguous_indices(len(frames), spec.get('start', 0), spec['max_frames'])
    return [downscale_if_needed(frames[i]) for i in indices]


def import_character(char_id: str, plan: dict) -> None:
    char_dir = YAHA_ASSETS / char_id
    if not char_dir.is_dir():
        raise FileNotFoundError(f'Character assets not found: {char_dir}')

    out = OUT_DIR / char_id
    out.mkdir(parents=True, exist_ok=True)

    animations: dict = {}
    preview_sheet = None

    for state, spec in plan['states'].items():
        frames = collect_state_frames(char_dir, spec)
        sheet, fw, fh = build_sprite_sheet(frames)
        file_name = f'{state}.png'
        sheet.save(out / file_name)
        animations[state] = {
            'file': file_name,
            'loop': True,
            'sprite': {
                'frameWidth': fw,
                'frameHeight': fh,
                'frameCount': len(frames),
                'columns': len(frames),
                'fps': spec['fps'],
                'startFrame': 0,
            },
        }
        if state == 'walk':
            preview_sheet = sheet

    if preview_sheet is not None:
        preview_sheet.save(out / 'skin.png')
        fw0 = animations['walk']['sprite']['frameWidth']
        fh0 = animations['walk']['sprite']['frameHeight']
        preview_sheet.crop((0, 0, fw0, fh0)).save(out / 'pet.png')

    fw = animations['walk']['sprite']['frameWidth']
    fh = animations['walk']['sprite']['frameHeight']
    skin = {
        'name': plan['name'],
        'version': '1.0.1',
        'author': 'Yaha-Pet (fan import)',
        'source': 'https://github.com/gitChara-dot/Yaha-Pet',
        'license': 'MIT (assets: fan-made, Chiikawa IP by Nagano)',
        'description': plan['description'],
        'style': 'cartoon',
        'format': 'sprite',
        'size': display_size(fw, fh),
        'animations': animations,
    }
    with open(out / 'skin.json', 'w', encoding='utf-8') as f:
        json.dump(skin, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(f'✓ {char_id}: {out}')


def main() -> int:
    if not YAHA_ASSETS.is_dir():
        print(f'Missing Yaha-Pet assets at {YAHA_ASSETS}', file=sys.stderr)
        print('Clone first: git clone --depth 1 https://github.com/gitChara-dot/Yaha-Pet.git .tmp_chiikawa/Yaha-Pet', file=sys.stderr)
        return 1

    for char_id, plan in CHAR_PLANS.items():
        import_character(char_id, plan)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
