"""
core/live_vision_stream.py
Live multimodal screen and webcam vision streamer for Charlie AI Assistant.
Feeds compressed JPEG visual frames to Gemini Live API with frame-diff gating.
"""
from __future__ import annotations

import io
import time
import threading
from typing import Callable, Optional
from PIL import Image


class LiveVisionStreamer:
    """Manages adaptive screen & camera frame streaming to Gemini Live.

    Uses perceptual hashing (pHash) to skip visually redundant frames.
    Only frames where the Hamming distance to the previous sent frame
    exceeds `phash_threshold` are forwarded — eliminates blinking cursors,
    screensavers, and static UI elements without missing real changes.
    """

    def __init__(self, fps: float = 1.0, quality: int = 70,
                 max_dim: int = 1024, phash_threshold: int = 8):
        self.fps = fps
        self.quality = quality
        self.max_dim = max_dim
        self.phash_threshold = phash_threshold   # Hamming bits out of 64
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[bytes, str], None]] = None
        self._last_frame_bytes: Optional[bytes] = None
        self._last_phash: Optional[int] = None   # 64-bit integer hash
        self._source = "screen"  # "screen" or "camera"
        self._lock = threading.Lock()

    def set_listener(self, callback: Callable[[bytes, str], None]):
        """Sets callback for outgoing frames: callback(jpeg_bytes, mime_type)."""
        self._callback = callback

    def set_source(self, source: str):
        """Toggle source between 'screen' and 'camera'."""
        with self._lock:
            self._source = "camera" if source.lower() == "camera" else "screen"

    def start(self):
        """Starts background streaming loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True, name="LiveVisionStreamerThread")
        self._thread.start()

    def stop(self):
        """Stops background streaming."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def capture_screen_frame(self) -> Optional[Image.Image]:
        """Captures primary monitor image using mss or PIL."""
        try:
            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        except Exception:
            try:
                from PIL import ImageGrab
                return ImageGrab.grab()
            except Exception:
                return None

    def capture_camera_frame(self) -> Optional[Image.Image]:
        """Captures a single webcam frame using opencv."""
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return None
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return None
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return Image.fromarray(rgb)
        except Exception:
            return None

    # ── perceptual hash ────────────────────────────────────────────────────

    @staticmethod
    def _phash(img: Image.Image, hash_size: int = 8) -> int:
        """Compute a 64-bit average perceptual hash (aHash).
        Resize to hash_size×hash_size greyscale, compare each pixel to mean.
        Returns a 64-bit integer where set bits = pixels above mean.
        """
        small = img.convert("L").resize(
            (hash_size, hash_size), Image.Resampling.BILINEAR
        )
        pixels = list(small.getdata())
        mean = sum(pixels) / len(pixels)
        bits = 0
        for px in pixels:
            bits = (bits << 1) | (1 if px >= mean else 0)
        return bits

    @staticmethod
    def _hamming_distance(a: int, b: int) -> int:
        """Count differing bits between two 64-bit hashes."""
        x = a ^ b
        count = 0
        while x:
            count += x & 1
            x >>= 1
        return count

    def _compress_frame(self, img: Image.Image) -> bytes:
        """Downscale and compress to JPEG bytes."""
        w, h = img.size
        if max(w, h) > self.max_dim:
            scale = self.max_dim / float(max(w, h))
            img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self.quality, optimize=True)
        return buf.getvalue()

    def _stream_loop(self):
        """Background acquisition loop with adaptive throttling."""
        interval = 1.0 / max(0.2, self.fps)
        while self._running:
            start_t = time.monotonic()
            img = None
            with self._lock:
                src = self._source

            if src == "camera":
                img = self.capture_camera_frame()
            else:
                img = self.capture_screen_frame()

            if img and self._callback:
                try:
                    jpeg_bytes = self._compress_frame(img)
                    # Perceptual hash gate: only forward visually changed frames
                    new_hash = self._phash(img)
                    should_send = (
                        self._last_phash is None
                        or self._hamming_distance(new_hash, self._last_phash)
                           > self.phash_threshold
                    )
                    if should_send:
                        self._last_phash = new_hash
                        self._last_frame_bytes = jpeg_bytes
                        self._callback(jpeg_bytes, "image/jpeg")
                except Exception:
                    pass

            elapsed = time.monotonic() - start_t
            sleep_t = max(0.05, interval - elapsed)
            time.sleep(sleep_t)


_global_streamer: Optional[LiveVisionStreamer] = None


def get_vision_streamer() -> LiveVisionStreamer:
    global _global_streamer
    if _global_streamer is None:
        _global_streamer = LiveVisionStreamer(fps=1.0, quality=70)
    return _global_streamer
