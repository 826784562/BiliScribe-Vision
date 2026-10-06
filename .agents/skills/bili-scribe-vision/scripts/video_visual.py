#!/usr/bin/env python3
"""Local teaching-state detection and key frames for the current Codex's image tool.

No inference API is called. Supply verified windows for operations whose intermediate
states are not detected by the conservative pixel heuristic.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from common import digest, hms, read_json, seconds, write_json


def select_frames(segments: list[dict], mode: str = 'adaptive', loss_threshold: float = 0.25) -> list[dict]:
    selected = []
    ids = set()
    for segment in segments:
        lesson, sid = str(segment['lesson_id']), str(segment['segment_id'])
        if (lesson, sid) in ids:
            raise ValueError('duplicate lesson/segment identity')
        ids.add((lesson, sid))
        start, end = seconds(segment['start']), seconds(segment['end'])
        if end <= start:
            raise ValueError('segment end must follow start')
        candidates = sorted(segment.get('candidates', []), key=lambda c: seconds(c['timestamp']))
        if any(not start <= seconds(c['timestamp']) < end for c in candidates):
            raise ValueError(f'candidate outside segment {sid}')
        usable = [c for c in candidates if not c.get('transition') and not c.get('blank') and not c.get('occluded')]
        stable = [c for c in usable if c.get('stable', False)]
        completed = [c for c in stable if c.get('completed') is True]
        final = (completed or stable or usable or [None])[-1]
        chosen = []
        if final:
            chosen = [{**final, 'role': 'completed_state'}]
            earlier = [c for c in stable if seconds(c['timestamp']) < seconds(final['timestamp'])]
            if mode == 'adaptive' and earlier:
                backup = max(earlier, key=lambda c: float(c.get('completeness', 0)))
                peak, current = float(backup.get('completeness', 0)), float(final.get('completeness', 0))
                if peak > 0 and (peak - current) / peak >= loss_threshold:
                    chosen.insert(0, {**backup, 'role': 'pre_erase_backup'})
        frames = []
        for index, frame in enumerate(chosen, 1):
            timestamp = seconds(frame['timestamp'])
            frames.append({**frame, 'frame_id': f'{lesson}-{sid}-F{index}', 'timestamp': timestamp,
                           'timestamp_hms': hms(timestamp), 'used_in_output': False, 'entry_ids': []})
        selected.append({'lesson_id': lesson, 'segment_id': sid, 'type': segment.get('type', 'OTHER'),
                         'start': start, 'end': end, 'mode': mode, 'selected_frames': frames,
                         'boundary_source': segment.get('boundary_source', 'user-windows'),
                         'needs_human_review': not stable or not frames or bool(segment.get('complex')),
                         'selection_quality': 'heuristic' if not completed else 'verified-candidate'})
    return selected


def candidate_segments(path: Path, lesson_id: str, fps: float, frame_dir: Path,
                       windows: list[dict] | None = None, roi: tuple[int, int, int, int] | None = None,
                       change_threshold: float = 0.18, max_seconds: float = 300) -> list[dict]:
    import cv2
    if not math.isfinite(fps) or fps <= 0 or fps > 10 or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError('fps must be in (0, 10]; max segment length must be positive')
    if not 0 < change_threshold <= 1:
        raise ValueError('change threshold must be in (0, 1]')
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise ValueError(f'cannot open video: {path}')
    rate = capture.get(cv2.CAP_PROP_FPS)
    duration = capture.get(cv2.CAP_PROP_FRAME_COUNT) / rate if rate > 0 else 0
    if not math.isfinite(duration) or duration <= 0:
        capture.release(); raise ValueError('video has no reliable duration')
    frame_dir.mkdir(parents=True, exist_ok=True)
    # ponytail: pixel changes propose visual states, not semantic steps; the current
    # Codex verifies states and supplies --windows-json for missed click/parameter steps.
    segments, candidates = [], []
    previous, start, number = None, 0.0, 1
    interval = 1 / fps

    def finish(end: float, source: str):
        nonlocal candidates, start, number
        if candidates and end > start:
            segments.append({'lesson_id': lesson_id, 'segment_id': f'VS{number:04d}', 'type': 'OTHER',
                             'start': start, 'end': end, 'candidates': candidates, 'boundary_source': source})
            number += 1
        candidates, start = [], end

    def sample(timestamp: float):
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
        ok, frame = capture.read()
        if not ok:
            return None
        cropped = frame
        if roi:
            x, y, width, height = roi
            if min(x, y) < 0 or min(width, height) <= 0 or x + width > frame.shape[1] or y + height > frame.shape[0]:
                raise ValueError('ROI outside video')
            cropped = frame[y:y + height, x:x + width]
        gray = cv2.cvtColor(cv2.resize(cropped, (160, 90)), cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        return frame, gray

    def add(timestamp: float, frame, gray, diff: float):
        edges = cv2.Canny(gray, 40, 120)
        completeness = float((edges > 0).mean())
        image_path = frame_dir / f'{lesson_id}-{int(timestamp * 1000):010d}.jpg'
        ok, encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ok:
            raise ValueError('cannot encode candidate')
        encoded.tofile(str(image_path))
        candidates.append({'timestamp': timestamp, 'stable': diff < 0.015, 'difference': diff,
                           'completeness': completeness, 'blank': completeness < 0.001 and float(gray.std()) < 3,
                           'frame_path': str(image_path.resolve()), 'sha256': digest(image_path)})

    try:
        if windows is not None:
            previous_end = 0.0
            for window in windows:
                start, end = seconds(window['start']), seconds(window['end'])
                if start < previous_end or end <= start or end > duration + 0.1:
                    raise ValueError('windows must be ordered, nonoverlapping and within video')
                previous_end = end
                previous = None
                timestamp = start
                while timestamp < end:
                    sampled = sample(timestamp)
                    if sampled is None:
                        break
                    frame, gray = sampled
                    diff = 1.0 if previous is None else float(cv2.absdiff(gray, previous).mean()) / 255
                    add(timestamp, frame, gray, diff)
                    previous = gray; timestamp += interval
                count = len(segments)
                finish(end, 'user-windows')
                if len(segments) == count:
                    raise ValueError('window has no decodable frames')
                segments[-1]['type'] = window.get('type', 'OTHER')
                segments[-1]['complex'] = bool(window.get('complex'))
        else:
            timestamp = 0.0
            while timestamp < duration:
                sampled = sample(timestamp)
                if sampled is None:
                    break
                frame, gray = sampled
                diff = 1.0 if previous is None else float(cv2.absdiff(gray, previous).mean()) / 255
                changed = 0 if previous is None else float((cv2.absdiff(gray, previous) > 25).mean())
                # Keep small board erasures inside a segment so adaptive can retain history.
                if candidates and (changed >= change_threshold or timestamp - start >= max_seconds):
                    finish(timestamp, 'local-change' if changed >= change_threshold else 'length-cap')
                add(timestamp, frame, gray, diff)
                previous = gray; timestamp += interval
            finish(duration, 'local-change')
    finally:
        capture.release()
    if not segments:
        raise ValueError('no decodable video frames')
    return segments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--segments-json', type=Path)
    source.add_argument('--video', type=Path)
    parser.add_argument('--windows-json', type=Path, help='verified teaching/action windows for --video')
    parser.add_argument('-o', '--output', type=Path, default=Path('visual_manifest.json'))
    parser.add_argument('--lesson-id', default='L001')
    parser.add_argument('--visual-mode', choices=['final', 'adaptive'], default='adaptive')
    parser.add_argument('--fps', type=float, default=1.0)
    parser.add_argument('--change-threshold', type=float, default=0.18)
    parser.add_argument('--max-seconds', type=float, default=300)
    parser.add_argument('--roi', help='x,y,width,height for change detection; saved frames remain full size')
    parser.add_argument('--frame-dir', type=Path)
    args = parser.parse_args()
    try:
        if args.segments_json:
            raw = read_json(args.segments_json)
            segments = raw['segments'] if isinstance(raw, dict) else raw
            for segment in segments:
                for frame in segment.get('candidates', []):
                    path = Path(frame['frame_path'])
                    path = path if path.is_absolute() else args.segments_json.parent / path
                    frame['frame_path'] = str(path.resolve()); frame['sha256'] = digest(path)
        else:
            windows = read_json(args.windows_json) if args.windows_json else None
            if isinstance(windows, dict):
                windows = windows['segments']
            roi = tuple(map(int, args.roi.split(','))) if args.roi else None
            if roi and len(roi) != 4:
                raise ValueError('ROI needs four integers')
            frame_dir = args.frame_dir or Path('.cache/bili-scribe/visual_frames') / args.lesson_id
            segments = candidate_segments(args.video, args.lesson_id, args.fps, frame_dir, windows, roi,
                                          args.change_threshold, args.max_seconds)
        selected = select_frames(segments, args.visual_mode)
        manifest = {'schema_version': 2, 'mode': args.visual_mode, 'source': str((args.video or args.segments_json).resolve()),
                    'segments': selected, 'selected_frame_count': sum(len(s['selected_frames']) for s in selected),
                    'model_images_reviewed': 0, 'selection_is_understanding': False}
        write_json(args.output, manifest)
        print(f"[done] {len(selected)} visual states, {manifest['selected_frame_count']} selected frames -> {args.output}")
        print('[next] current Codex must read aligned text and open selected images; verify operational steps before drafting')
        return 0
    except (ValueError, KeyError, OSError, TypeError, ImportError) as error:
        print(f'[error] {error}', file=sys.stderr); return 1


if __name__ == '__main__':
    raise SystemExit(main())
