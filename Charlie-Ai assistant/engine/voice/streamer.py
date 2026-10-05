"""engine/voice/streamer.py — Pipelined Asynchronous Audio Streaming Engine.

Delivers ultra-low latency voice responses by synthesizing and playing text
chunk-by-chunk on sentence boundaries. While sentence N plays through the
audio hardware, sentence N+1 synthesizes concurrently in the background.
"""
from __future__ import annotations

import logging
import queue
import re
import threading
import time
from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Union

import numpy as np
import sounddevice as sd

logger = logging.getLogger("charlie.voice.streamer")

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=\n)\s*\n")


class StreamAudioChunk:
    """Represents a synthesized audio segment ready for playback."""
    def __init__(self, sentence: str, samples: np.ndarray, sample_rate: int, index: int):
        self.sentence = sentence
        self.samples = samples
        self.sample_rate = sample_rate
        self.index = index


class AsyncAudioStreamer:
    """Sentence-pipelined asynchronous TTS audio streamer with instant barge-in support."""

    def __init__(self):
        self._sentence_queue: queue.Queue[Optional[tuple[int, str]]] = queue.Queue()
        self._audio_queue: queue.Queue[Optional[StreamAudioChunk]] = queue.Queue(maxsize=4)
        self._stop_event = threading.Event()
        self._is_streaming = False
        self._active_stream_id = 0
        self._lock = threading.Lock()

        # Telemetry
        self._first_audio_latency_ms: float = 0.0
        self._total_sentences: int = 0
        self._total_play_sec: float = 0.0

        # Background worker threads
        self._synth_thread: Optional[threading.Thread] = None
        self._play_thread: Optional[threading.Thread] = None

    @property
    def is_streaming(self) -> bool:
        return self._is_streaming

    def stop(self) -> None:
        """Immediate cancellation and acoustic cutoff (<10ms)."""
        with self._lock:
            self._stop_event.set()
            self._active_stream_id += 1
            self._is_streaming = False

            # Drain queues
            while not self._sentence_queue.empty():
                try:
                    self._sentence_queue.get_nowait()
                    self._sentence_queue.task_done()
                except Exception:
                    break

            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                    self._audio_queue.task_done()
                except Exception:
                    break

        try:
            sd.stop()
        except Exception:
            pass

    def stream_sentences(
        self,
        sentences: Iterable[str],
        voice: str = "",
        speed: float = 1.0,
        volume: float = 1.0,
        on_sentence_start: Optional[Callable[[str], None]] = None,
        on_finish: Optional[Callable[[], None]] = None,
    ) -> None:
        """Stream an iterable/generator of sentences with concurrent synthesis and playback."""
        self.stop()  # Clean any prior stream

        with self._lock:
            self._stop_event.clear()
            self._is_streaming = True
            current_stream_id = self._active_stream_id

        t_start = time.perf_counter()
        first_audio_marked = False

        def _synth_worker():
            for idx, text in enumerate(sentences):
                if self._stop_event.is_set() or self._active_stream_id != current_stream_id:
                    break
                s = text.strip()
                if not s:
                    continue

                samples, sr = self._synthesize_sentence(s, voice=voice, speed=speed, volume=volume)
                if samples is not None and len(samples) > 0:
                    chunk = StreamAudioChunk(sentence=s, samples=samples, sample_rate=sr, index=idx)
                    try:
                        self._audio_queue.put(chunk, timeout=5.0)
                    except queue.Full:
                        pass

            # Sentinel for playback completion
            try:
                self._audio_queue.put(None, timeout=2.0)
            except Exception:
                pass

        def _play_worker():
            nonlocal first_audio_marked
            try:
                while not self._stop_event.is_set() and self._active_stream_id == current_stream_id:
                    try:
                        chunk = self._audio_queue.get(timeout=0.2)
                    except queue.Empty:
                        continue

                    if chunk is None:
                        self._audio_queue.task_done()
                        break

                    if not first_audio_marked:
                        self._first_audio_latency_ms = (time.perf_counter() - t_start) * 1000.0
                        first_audio_marked = True

                    if on_sentence_start:
                        try:
                            on_sentence_start(chunk.sentence)
                        except Exception:
                            pass

                    # Play chunk
                    self._play_samples(chunk.samples, chunk.sample_rate)
                    self._audio_queue.task_done()
            finally:
                with self._lock:
                    if self._active_stream_id == current_stream_id:
                        self._is_streaming = False
                if on_finish and not self._stop_event.is_set():
                    try:
                        on_finish()
                    except Exception:
                        pass

        self._synth_thread = threading.Thread(target=_synth_worker, daemon=True, name="AsyncAudioSynth")
        self._play_thread = threading.Thread(target=_play_worker, daemon=True, name="AsyncAudioPlayer")
        self._synth_thread.start()
        self._play_thread.start()

    def stream_text(
        self,
        full_text: str,
        voice: str = "",
        speed: float = 1.0,
        volume: float = 1.0,
        on_sentence_start: Optional[Callable[[str], None]] = None,
        on_finish: Optional[Callable[[], None]] = None,
    ) -> None:
        """Split a complete text block into sentence streams and play with pipeline concurrency."""
        if not full_text or not full_text.strip():
            if on_finish:
                on_finish()
            return

        raw_parts = _SENT_SPLIT.split(full_text)
        sentences = [p.strip() for p in raw_parts if p.strip()]
        if not sentences:
            sentences = [full_text.strip()]

        self.stream_sentences(
            sentences=sentences,
            voice=voice,
            speed=speed,
            volume=volume,
            on_sentence_start=on_sentence_start,
            on_finish=on_finish,
        )

    def _synthesize_sentence(
        self,
        text: str,
        voice: str = "",
        speed: float = 1.0,
        volume: float = 1.0,
    ) -> tuple[Optional[np.ndarray], int]:
        """Synthesize text to float32 numpy samples via EdgeTTS or SAPI5 fallback."""
        try:
            import asyncio
            from core.tts import EdgeTTSEngine
            engine = EdgeTTSEngine(voice=voice or "en-US-ChristopherNeural")
            loop = asyncio.new_event_loop()
            try:
                audio_bytes, _ = loop.run_until_complete(
                    engine._synth_with_boundaries(text)
                )
            finally:
                loop.close()

            if audio_bytes:
                import miniaudio
                decoded = miniaudio.decode(
                    audio_bytes,
                    output_format=miniaudio.SampleFormat.FLOAT32,
                    nchannels=1,
                )
                samples = np.array(decoded.samples, dtype=np.float32)
                if volume != 1.0:
                    samples = samples * max(0.0, min(2.0, volume))
                return samples, decoded.sample_rate
        except Exception as e:
            logger.debug(f"Direct EdgeTTS synthesis failed ({e}), falling back to SAPI5")

        # Fallback: Windows SAPI5 or offline synthesis
        try:
            from core.tts import WindowsSAPITTSEngine
            sapi = WindowsSAPITTSEngine(voice=voice)
            sapi.speak(text)
            return None, 24000
        except Exception:
            return None, 24000

    def _play_samples(self, samples: np.ndarray, sample_rate: int) -> None:
        """Play audio samples via sounddevice while continuously checking for interrupt."""
        if samples is None or len(samples) == 0:
            return

        try:
            from core.tts import _get_output_device_idx
            dev = _get_output_device_idx()
        except Exception:
            dev = None

        try:
            sd.play(samples, sample_rate, device=dev)
            dur = len(samples) / float(sample_rate)
            t_end = time.perf_counter() + dur
            while time.perf_counter() < t_end:
                if self._stop_event.is_set():
                    sd.stop()
                    break
                time.sleep(0.02)
        except Exception as e:
            logger.error(f"Error during audio stream playback: {e}")

    def stats(self) -> Dict[str, Any]:
        """Return streaming telemetry."""
        return {
            "first_audio_latency_ms": round(self._first_audio_latency_ms, 2),
            "is_streaming": self._is_streaming,
            "queue_depth": self._audio_queue.qsize(),
        }


# Global Singleton
_streamer_instance: Optional[AsyncAudioStreamer] = None


def get_audio_streamer() -> AsyncAudioStreamer:
    """Access global async audio streamer singleton."""
    global _streamer_instance
    if _streamer_instance is None:
        _streamer_instance = AsyncAudioStreamer()
    return _streamer_instance
