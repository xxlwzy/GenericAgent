#!/usr/bin/env python3
"""Convert a short cat/pet video into a desktop-pet skin (sprite sheets + skin.json)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from rembg import remove

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / 'frontends' / 'skins'
DISPLAY_HEIGHT = 128
MAX_SOURCE_DIM = 256


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Convert a pet video into a desktop-pet skin.')
    p.add_argument('video', type=Path, help='Input video path (mp4/mov/...)')
    p.add_argument('--skin-id', default='', help='Skin folder name (default: video stem)')
    p.add_argument('--name', default='', help='Display name in skin.json')
    p.add_argument('--description', default='', help='Skin description')
    p.add_argument('--start', type=float, default=0.05, help='Search range start (ratio 0-1)')
    p.add_argument('--end', type=float, default=0.75, help='Search range end (ratio 0-1)')
    p.add_argument('--loop-frames', type=int, default=14, help='Frames in one smooth loop')
    p.add_argument('--sample-step', type=int, default=2, help='Source frame step (2=every 2nd frame)')
    p.add_argument('--idle-fps', type=int, default=3)
    p.add_argument('--walk-fps', type=int, default=5)
    p.add_argument('--run-fps', type=int, default=8)
    p.add_argument('--sprint-fps', type=int, default=12)
    p.add_argument('--no-remove-bg', action='store_true', help='Skip background removal')
    return p.parse_args()


def slugify(stem: str) -> str:
    s = stem.strip().lower().replace(' ', '-')
    return ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in s).strip('-') or 'my-pet'


def read_frame_at(cap: cv2.VideoCapture, idx: int) -> Image.Image | None:
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, bgr = cap.read()
    if not ok:
        return None
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def motion_fingerprint(img: Image.Image, size: int = 96) -> np.ndarray:
    small = img.convert('L').resize((size, size), Image.Resampling.BILINEAR)
    return np.asarray(small, dtype=np.float32)


def frame_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def find_smooth_loop(
    cap: cv2.VideoCapture,
    start_idx: int,
    end_idx: int,
    step: int,
    loop_len: int,
) -> tuple[list[int], float]:
    """Pick a contiguous source-frame window with low motion and good loop closure."""
    probe_indices = list(range(start_idx, end_idx + 1, step))
    fingerprints: list[np.ndarray] = []
    valid_indices: list[int] = []

    for idx in probe_indices:
        frame = read_frame_at(cap, idx)
        if frame is None:
            continue
        fingerprints.append(motion_fingerprint(frame))
        valid_indices.append(idx)

    if len(valid_indices) < loop_len:
        raise RuntimeError(f'Not enough frames for loop (need {loop_len}, got {len(valid_indices)})')

    best_score = float('inf')
    best_start = 0
    for start in range(0, len(valid_indices) - loop_len + 1):
        window = fingerprints[start:start + loop_len]
        motion = sum(frame_distance(window[i], window[i + 1]) for i in range(loop_len - 1)) / (loop_len - 1)
        loop_gap = frame_distance(window[0], window[-1])
        score = motion * 0.75 + loop_gap * 0.25
        if score < best_score:
            best_score = score
            best_start = start

    chosen = valid_indices[best_start:best_start + loop_len]
    # Expand to every source frame between first and last for maximum continuity.
    dense = list(range(chosen[0], chosen[-1] + 1))
    if len(dense) > loop_len:
        # Evenly subsample dense range but keep endpoints for loop closure.
        pick = np.linspace(0, len(dense) - 1, loop_len, dtype=int)
        chosen = [dense[i] for i in pick]
    elif len(dense) < loop_len:
        chosen = dense
        while len(chosen) < loop_len:
            chosen.append(chosen[-1])

    print(f'  loop window: frames {chosen[0]}..{chosen[-1]} (score={best_score:.2f})')
    return chosen, best_score


def load_loop_frames(video: Path, indices: list[int]) -> list[Image.Image]:
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video: {video}')
    frames: list[Image.Image] = []
    for idx in indices:
        frame = read_frame_at(cap, idx)
        if frame is not None:
            frames.append(frame)
    cap.release()
    if not frames:
        raise RuntimeError('Failed to read loop frames')
    return frames


def remove_background(img: Image.Image) -> Image.Image:
    return remove(img.convert('RGBA')).convert('RGBA')


def alpha_bbox(img: Image.Image, threshold: int = 12) -> tuple[int, int, int, int] | None:
    alpha = np.array(img.getchannel('A'))
    ys, xs = np.where(alpha > threshold)
    if len(xs) == 0:
        return None
    pad = 6
    left = max(0, int(xs.min()) - pad)
    top = max(0, int(ys.min()) - pad)
    right = min(img.width, int(xs.max()) + pad + 1)
    bottom = min(img.height, int(ys.max()) + pad + 1)
    return left, top, right, bottom


def union_bbox(images: list[Image.Image]) -> tuple[int, int, int, int]:
    box = None
    for img in images:
        b = alpha_bbox(img)
        if b is None:
            continue
        box = b if box is None else (
            min(box[0], b[0]), min(box[1], b[1]),
            max(box[2], b[2]), max(box[3], b[3]),
        )
    if box is None:
        w, h = images[0].size
        return (0, 0, w, h)
    return box


def centroid(img: Image.Image) -> tuple[float, float]:
    alpha = np.array(img.getchannel('A'))
    ys, xs = np.where(alpha > 20)
    if len(xs) == 0:
        return img.width / 2, img.height / 2
    return float(xs.mean()), float(ys.mean())


def downscale(img: Image.Image) -> Image.Image:
    longest = max(img.width, img.height)
    if longest <= MAX_SOURCE_DIM:
        return img
    scale = MAX_SOURCE_DIM / longest
    size = (max(1, int(round(img.width * scale))), max(1, int(round(img.height * scale))))
    return img.resize(size, Image.Resampling.LANCZOS)


def align_frames(frames: list[Image.Image]) -> tuple[list[Image.Image], int, int]:
    """Bottom-align frames and stabilize horizontal position by median centroid."""
    max_w = max(img.width for img in frames)
    max_h = max(img.height for img in frames)
    centers = [centroid(img) for img in frames]
    target_x = float(np.median([c[0] for c in centers]))

    out: list[Image.Image] = []
    for img, (cx, _) in zip(frames, centers):
        canvas = Image.new('RGBA', (max_w, max_h), (0, 0, 0, 0))
        x = int(round(target_x - cx + (max_w - img.width) / 2))
        x = max(0, min(x, max_w - img.width))
        y = max_h - img.height
        canvas.paste(img, (x, y), img)
        out.append(canvas)
    return out, max_w, max_h


def build_sprite_sheet(frames: list[Image.Image]) -> tuple[Image.Image, int, int]:
    normalized, fw, fh = align_frames(frames)
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


def build_skin(
    video: Path,
    skin_id: str,
    display_name: str,
    description: str,
    loop_frames: list[Image.Image],
    fps_map: dict[str, int],
    remove_bg: bool,
) -> Path:
    print(f'Processing {len(loop_frames)} loop frames...')
    processed: list[Image.Image] = []
    for i, frame in enumerate(loop_frames):
        img = frame if remove_bg else frame.convert('RGBA')
        if remove_bg:
            print(f'  remove bg {i + 1}/{len(loop_frames)}', flush=True)
            img = remove_background(img)
        processed.append(img)

    box = union_bbox(processed)
    cropped = [downscale(img.crop(box)) for img in processed]

    out = OUT_DIR / skin_id
    out.mkdir(parents=True, exist_ok=True)

    animations = {}
    preview = None
    for state, fps in fps_map.items():
        sheet, fw, fh = build_sprite_sheet(cropped)
        file_name = f'{state}.png'
        sheet.save(out / file_name)
        animations[state] = {
            'file': file_name,
            'loop': True,
            'sprite': {
                'frameWidth': fw,
                'frameHeight': fh,
                'frameCount': len(cropped),
                'columns': len(cropped),
                'fps': fps,
                'startFrame': 0,
            },
        }
        if state == 'walk':
            preview = sheet

    if preview is not None:
        preview.save(out / 'skin.png')
        fw0 = animations['walk']['sprite']['frameWidth']
        fh0 = animations['walk']['sprite']['frameHeight']
        preview.crop((0, 0, fw0, fh0)).save(out / 'pet.png')

    fw = animations['walk']['sprite']['frameWidth']
    fh = animations['walk']['sprite']['frameHeight']
    skin = {
        'name': display_name,
        'version': '1.0.1',
        'author': 'video import',
        'source': str(video.expanduser().resolve()),
        'license': 'personal use',
        'description': description,
        'style': 'photo',
        'format': 'sprite',
        'size': display_size(fw, fh),
        'animations': animations,
    }
    with open(out / 'skin.json', 'w', encoding='utf-8') as f:
        json.dump(skin, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(f'✓ Skin saved to {out}')
    return out


def main() -> int:
    args = parse_args()
    video = args.video.expanduser().resolve()
    if not video.is_file():
        print(f'Video not found: {video}', file=sys.stderr)
        return 1

    skin_id = args.skin_id or slugify(video.stem)
    display_name = args.name or video.stem
    description = args.description or f'从视频导入：{video.name}'

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        print(f'Cannot open video: {video}', file=sys.stderr)
        return 1
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    start_idx = max(0, int(total * args.start))
    end_idx = min(total - 1, int(total * args.end))
    print(f'Searching smooth loop in frames {start_idx}..{end_idx} (step={args.sample_step})...')
    indices, _score = find_smooth_loop(cap, start_idx, end_idx, args.sample_step, args.loop_frames)
    cap.release()

    loop_frames = load_loop_frames(video, indices)
    fps_map = {
        'idle': args.idle_fps,
        'walk': args.walk_fps,
        'run': args.run_fps,
        'sprint': args.sprint_fps,
    }
    build_skin(
        video=video,
        skin_id=skin_id,
        display_name=display_name,
        description=description,
        loop_frames=loop_frames,
        fps_map=fps_map,
        remove_bg=not args.no_remove_bg,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
