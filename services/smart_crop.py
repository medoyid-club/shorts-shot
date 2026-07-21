"""
Smart crop / layout for vertical Shorts (9:16).
OpenCV Haar face detection — local and fast.

Returns focus + fit mode:
- cover  — full-bleed (portrait photos, already vertical media)
- contain — landscape / talking-head: media fills upper stage above chyron
            (cover within ~top 52%), soft dark below — no full-frame letterbox blur

Multiple faces: dominant vs union (same as before).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("smart_crop")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".avi"}
DOMINANT_FACE_RATIO = 2.5
FACE_Y_BIAS = 0.18
MAX_FACES_IN_UNION = 3
DEFAULT_FOCUS = (0.5, 0.32)
VIDEO_SAMPLE_SECONDS = (0.5, 1.0, 1.5, 0.0)
# Landscape or large face → show full frame (less "digital zoom")
LANDSCAPE_ASPECT = 1.15
LARGE_FACE_RATIO = 0.28


@dataclass
class MediaLayout:
    focus_x: float
    focus_y: float
    fit: str  # "cover" | "contain"
    face_ratio: float
    aspect: float
    strategy: str

    @property
    def focus_css(self) -> str:
        return f"{self.focus_x * 100:.1f}% {self.focus_y * 100:.1f}%"


def _load_cascade() -> Optional[cv2.CascadeClassifier]:
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    if not cascade_path.is_file():
        logger.warning("⚠️ Haar cascade не найден: %s", cascade_path)
        return None
    cascade = cv2.CascadeClassifier(str(cascade_path))
    if cascade.empty():
        logger.warning("⚠️ Не удалось загрузить Haar cascade")
        return None
    return cascade


def _detect_faces(gray: np.ndarray, cascade: cv2.CascadeClassifier) -> List[Tuple[int, int, int, int]]:
    h, w = gray.shape[:2]
    max_side = max(h, w)
    scale = 1.0
    work = gray
    if max_side > 1280:
        scale = 1280 / max_side
        work = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    faces = cascade.detectMultiScale(
        work,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(max(24, int(40 * scale)), max(24, int(40 * scale))),
        flags=cv2.CASCADE_SCALE_IMAGE,
    )
    if faces is None or len(faces) == 0:
        return []

    out: List[Tuple[int, int, int, int]] = []
    inv = 1.0 / scale
    for (x, y, fw, fh) in faces:
        out.append((int(x * inv), int(y * inv), int(fw * inv), int(fh * inv)))
    out.sort(key=lambda b: b[2] * b[3], reverse=True)
    return out


def _focus_from_boxes(
    boxes: List[Tuple[int, int, int, int]],
    img_w: int,
    img_h: int,
) -> Tuple[float, float, str, float]:
    """Returns fx, fy, strategy, face_height_ratio."""
    if not boxes:
        return DEFAULT_FOCUS[0], DEFAULT_FOCUS[1], "center", 0.0

    if len(boxes) == 1:
        chosen = boxes[:1]
        strategy = "single_face"
    else:
        a0 = boxes[0][2] * boxes[0][3]
        a1 = boxes[1][2] * boxes[1][3]
        if a1 > 0 and (a0 / a1) >= DOMINANT_FACE_RATIO:
            chosen = boxes[:1]
            strategy = "dominant_face"
        else:
            chosen = boxes[: min(MAX_FACES_IN_UNION, len(boxes))]
            strategy = f"union_{len(chosen)}_faces"

    xs = [b[0] for b in chosen]
    ys = [b[1] for b in chosen]
    rights = [b[0] + b[2] for b in chosen]
    bottoms = [b[1] + b[3] for b in chosen]
    x0, y0 = min(xs), min(ys)
    x1, y1 = max(rights), max(bottoms)
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    box_h = max(1.0, y1 - y0)
    cy = cy - FACE_Y_BIAS * box_h
    face_ratio = box_h / max(img_h, 1)

    # Keep subject in the upper band (above mid-frame chyron ~46%)
    fx = float(np.clip(cx / max(img_w, 1), 0.08, 0.92))
    fy = float(np.clip(cy / max(img_h, 1), 0.08, 0.55))
    return fx, fy, strategy, float(face_ratio)


def _choose_fit(aspect: float, face_ratio: float) -> str:
    """
    contain — landscape / large face: upper stage above chyron (no full-frame letterbox).
    cover  — portrait / vertical media: full-bleed.
    """
    if aspect >= LANDSCAPE_ASPECT:
        return "contain"
    if face_ratio >= LARGE_FACE_RATIO:
        return "contain"
    return "cover"


def _layout_from_bgr(
    img: np.ndarray,
    cascade: cv2.CascadeClassifier,
    label: str,
) -> MediaLayout:
    h, w = img.shape[:2]
    aspect = w / max(h, 1)
    gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    faces = _detect_faces(gray, cascade)
    fx, fy, strategy, face_ratio = _focus_from_boxes(faces, w, h)
    fit = _choose_fit(aspect, face_ratio)
    # contain: фокус в верхней трети — медиа живёт в сцене над шитроном
    if fit == "contain":
        if faces:
            fx = float(np.clip(fx, 0.15, 0.85))
            fy = float(np.clip(fy, 0.18, 0.42))
        else:
            fx, fy = 0.5, 0.30
    return MediaLayout(
        focus_x=fx,
        focus_y=fy,
        fit=fit,
        face_ratio=face_ratio,
        aspect=aspect,
        strategy=f"{strategy}@{label}",
    )


def _read_image_bgr(path: Path) -> Optional[np.ndarray]:
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        img = cv2.imread(str(path))
    return img


def _sample_video_frames(path: Path) -> List[Tuple[str, np.ndarray]]:
    import os
    import shutil
    import tempfile

    tmp_copy: Optional[Path] = None
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        try:
            suffix = path.suffix or ".mp4"
            fd, tmp_name = tempfile.mkstemp(prefix="smartcrop_", suffix=suffix)
            os.close(fd)
            tmp_copy = Path(tmp_name)
            shutil.copy2(path, tmp_copy)
            cap = cv2.VideoCapture(str(tmp_copy))
        except Exception as e:
            logger.warning("⚠️ smart_crop: fallback-копия видео не удалась: %s", e)

    if not cap.isOpened():
        logger.warning("⚠️ smart_crop: не удалось открыть видео %s", path.name)
        if tmp_copy and tmp_copy.exists():
            try:
                tmp_copy.unlink()
            except OSError:
                pass
        return []

    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = (frame_count / fps) if fps > 1e-3 and frame_count > 0 else 0.0

        samples: List[Tuple[str, np.ndarray]] = []
        seen_pos: set[int] = set()
        for sec in VIDEO_SAMPLE_SECONDS:
            t = min(sec, max(0.0, duration * 0.85)) if duration > 0 else sec
            pos = int(round(t * fps)) if fps > 1e-3 else 0
            if pos in seen_pos:
                continue
            seen_pos.add(pos)
            cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
            ok, frame = cap.read()
            if ok and frame is not None:
                samples.append((f"t={t:.1f}s", frame))
        if not samples:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
            if ok and frame is not None:
                samples.append(("t=0.0s", frame))
        return samples
    finally:
        cap.release()
        if tmp_copy and tmp_copy.exists():
            try:
                tmp_copy.unlink()
            except OSError:
                pass


def compute_media_layout(media_path: str) -> MediaLayout:
    """Full layout hint for the Shorts template."""
    default = MediaLayout(
        focus_x=DEFAULT_FOCUS[0],
        focus_y=DEFAULT_FOCUS[1],
        fit="cover",
        face_ratio=0.0,
        aspect=1.0,
        strategy="default",
    )
    path = Path(media_path) if media_path else None
    if not path or not path.is_file():
        return default

    ext = path.suffix.lower()
    cascade = _load_cascade()
    if cascade is None:
        return default

    try:
        if ext in IMAGE_EXTS:
            img = _read_image_bgr(path)
            if img is None:
                logger.warning("⚠️ smart_crop: не удалось прочитать %s", path.name)
                return default
            layout = _layout_from_bgr(img, cascade, "image")
            logger.info(
                "🎯 smart_crop %s: fit=%s faces_ratio=%.2f aspect=%.2f strategy=%s focus=(%.2f, %.2f)",
                path.name,
                layout.fit,
                layout.face_ratio,
                layout.aspect,
                layout.strategy,
                layout.focus_x,
                layout.focus_y,
            )
            return layout

        if ext in VIDEO_EXTS:
            frames = _sample_video_frames(path)
            if not frames:
                return default

            best_layout: Optional[MediaLayout] = None
            best_score = (-1, -1)
            for label, frame in frames:
                layout = _layout_from_bgr(frame, cascade, label)
                area = int(layout.face_ratio * 10000)
                n_proxy = 1 if layout.face_ratio > 0 else 0
                score = (n_proxy, area)
                if score > best_score:
                    best_score = score
                    best_layout = layout

            assert best_layout is not None
            logger.info(
                "🎯 smart_crop video %s: fit=%s face_ratio=%.2f aspect=%.2f strategy=%s focus=(%.2f, %.2f) samples=%s",
                path.name,
                best_layout.fit,
                best_layout.face_ratio,
                best_layout.aspect,
                best_layout.strategy,
                best_layout.focus_x,
                best_layout.focus_y,
                len(frames),
            )
            return best_layout

        return default
    except Exception as e:
        logger.warning("⚠️ smart_crop ошибка для %s: %s", path, e)
        return default


def compute_media_focus(media_path: str) -> Tuple[float, float]:
    layout = compute_media_layout(media_path)
    return layout.focus_x, layout.focus_y


def compute_image_focus(media_path: str) -> Tuple[float, float]:
    return compute_media_focus(media_path)


def focus_to_css_percent(fx: float, fy: float) -> str:
    return f"{fx * 100:.1f}% {fy * 100:.1f}%"
