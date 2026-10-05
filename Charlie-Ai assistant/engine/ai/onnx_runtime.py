"""engine/ai/onnx_runtime.py — GPU-Accelerated ONNX Runtime Engine.

Provides automated hardware provider detection (DirectML, CUDA, TensorRT, CPU),
graph optimizations, session caching, and low-latency inference for local AI models.
"""
from __future__ import annotations

import logging
import os
import platform
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger("charlie.ai.onnx")


class ONNXRuntimeManager:
    """Manages GPU-accelerated ONNX Runtime sessions, hardware providers, and inference dispatch."""

    def __init__(self):
        self._sessions: Dict[str, Any] = {}
        self._session_providers: Dict[str, List[str]] = {}
        self._model_paths: Dict[str, Union[str, Path]] = {}
        self._lock = threading.Lock()
        self._available_providers = self._query_available_providers()
        self._preferred_providers = self._resolve_preferred_providers()

        # Telemetry
        self._inference_count = 0
        self._total_latency_sec = 0.0

        logger.info(
            f"[ONNX] Initialized. Available={self._available_providers} Preferred={self._preferred_providers}"
        )

    @staticmethod
    def _query_available_providers() -> List[str]:
        try:
            import onnxruntime as ort
            return list(ort.get_available_providers())
        except Exception as e:
            logger.warning(f"Could not query onnxruntime providers: {e}")
            return ["CPUExecutionProvider"]

    def _resolve_preferred_providers(self) -> List[Union[str, Tuple[str, Dict[str, Any]]]]:
        """Order execution providers by hardware acceleration speed."""
        providers: List[Union[str, Tuple[str, Dict[str, Any]]]] = []
        avail = set(self._available_providers)

        # 1. NVIDIA TensorRT
        if "TensorrtExecutionProvider" in avail:
            providers.append("TensorrtExecutionProvider")

        # 2. NVIDIA CUDA
        if "CUDAExecutionProvider" in avail:
            cuda_opts = {
                "device_id": 0,
                "arena_extend_strategy": "kNextPowerOfTwo",
                "gpu_mem_limit": 2 * 1024 * 1024 * 1024,  # 2 GB default
                "cudnn_conv_algo_search": "EXHAUSTIVE",
                "do_copy_in_default_stream": True,
            }
            providers.append(("CUDAExecutionProvider", cuda_opts))

        # 3. DirectML (Hardware acceleration for AMD, Intel Arc/Iris, NVIDIA on Windows)
        if "DmlExecutionProvider" in avail:
            dml_opts = {
                "device_id": 0,
            }
            providers.append(("DmlExecutionProvider", dml_opts))

        # 4. OpenVINO (Intel CPU/GPU/NPU)
        if "OpenVINOExecutionProvider" in avail:
            providers.append("OpenVINOExecutionProvider")

        # 5. CoreML (macOS Apple Silicon)
        if "CoreMLExecutionProvider" in avail:
            providers.append("CoreMLExecutionProvider")

        # 6. Fallback CPU
        providers.append("CPUExecutionProvider")
        return providers

    def get_preferred_providers(self) -> List[Union[str, Tuple[str, Dict[str, Any]]]]:
        return list(self._preferred_providers)

    def is_gpu_accelerated(self) -> bool:
        """Returns True if a hardware GPU provider is active."""
        for p in self._preferred_providers:
            name = p if isinstance(p, str) else p[0]
            if name in ("DmlExecutionProvider", "CUDAExecutionProvider", "TensorrtExecutionProvider"):
                return True
        return False

    def get_hardware_summary(self) -> Dict[str, Any]:
        """Provides runtime acceleration summary."""
        active_gpu = None
        for p in self._preferred_providers:
            name = p if isinstance(p, str) else p[0]
            if name in ("CUDAExecutionProvider", "DmlExecutionProvider", "TensorrtExecutionProvider"):
                active_gpu = name
                break

        return {
            "has_gpu_acceleration": self.is_gpu_accelerated(),
            "primary_provider": active_gpu or "CPUExecutionProvider",
            "available_providers": self._available_providers,
            "platform": platform.system(),
            "cached_sessions": len(self._sessions),
            "inferences_executed": self._inference_count,
            "avg_latency_ms": round((self._total_latency_sec / self._inference_count * 1000.0), 2)
            if self._inference_count > 0
            else 0.0,
        }

    def create_optimized_session(
        self,
        model_path_or_bytes: Union[str, Path, bytes],
        providers: Optional[List[Any]] = None,
        intra_threads: Optional[int] = None,
    ) -> Any:
        """Instantiates an inference session with graph optimizations."""
        import onnxruntime as ort

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        sess_options.enable_mem_pattern = True
        sess_options.enable_cpu_mem_arena = True

        cores = os.cpu_count() or 4
        sess_options.intra_op_num_threads = intra_threads or max(1, min(8, cores // 2))
        sess_options.inter_op_num_threads = 1

        chosen_providers = providers or self._preferred_providers

        # Try hardware providers first, fallback to CPU on initialization error
        try:
            session = ort.InferenceSession(
                model_path_or_bytes,
                sess_options=sess_options,
                providers=chosen_providers,
            )
            return session
        except Exception as e:
            logger.warning(
                f"[ONNX] Primary provider initialisation failed ({e}), falling back to CPUExecutionProvider"
            )
            return ort.InferenceSession(
                model_path_or_bytes,
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )

    def get_or_create_session(
        self,
        model_key: str,
        model_path: Union[str, Path],
        providers: Optional[List[Any]] = None,
    ) -> Any:
        """Returns cached session or initializes a new one thread-safely."""
        with self._lock:
            if model_key in self._sessions:
                return self._sessions[model_key]

            session = self.create_optimized_session(model_path, providers=providers)
            self._sessions[model_key] = session
            self._model_paths[model_key] = model_path
            active = session.get_providers()
            self._session_providers[model_key] = active
            logger.info(f"[ONNX] Session '{model_key}' ready with providers: {active}")
            return session

    def run_inference(
        self,
        model_key: str,
        input_feed: Dict[str, np.ndarray],
        output_names: Optional[List[str]] = None,
    ) -> List[np.ndarray]:
        """Executes inference on a cached session with performance telemetry and GPU->CPU fallback."""
        session = self._sessions.get(model_key)
        if session is None:
            raise KeyError(f"Session '{model_key}' not found. Load session with get_or_create_session first.")

        t0 = time.perf_counter()
        try:
            results = session.run(output_names, input_feed)
            dt = time.perf_counter() - t0
            with self._lock:
                self._inference_count += 1
                self._total_latency_sec += dt
            return results
        except Exception as e:
            logger.warning(f"[ONNX] Inference failure on '{model_key}' with primary provider: {e}")
            # Hardware fallback: if session wasn't already purely CPU, rebuild session on CPU and retry once
            current_providers = self._session_providers.get(model_key, [])
            model_path = self._model_paths.get(model_key)
            if model_path and (not current_providers or current_providers[0] != "CPUExecutionProvider"):
                logger.info(f"[ONNX] Falling back '{model_key}' to CPUExecutionProvider...")
                try:
                    cpu_session = self.create_optimized_session(model_path, providers=["CPUExecutionProvider"])
                    with self._lock:
                        self._sessions[model_key] = cpu_session
                        self._session_providers[model_key] = ["CPUExecutionProvider"]
                    results = cpu_session.run(output_names, input_feed)
                    dt = time.perf_counter() - t0
                    with self._lock:
                        self._inference_count += 1
                        self._total_latency_sec += dt
                    logger.info(f"[ONNX] CPU fallback successful for '{model_key}'.")
                    return results
                except Exception as fallback_err:
                    logger.error(f"[ONNX] CPU fallback failed for '{model_key}': {fallback_err}")
                    raise
            raise

    def warmup(self, model_key: str, dummy_feed: Dict[str, np.ndarray]) -> bool:
        """Runs single dummy inference to compile execution kernels and avoid cold-start lag."""
        try:
            self.run_inference(model_key, dummy_feed)
            return True
        except Exception as e:
            logger.debug(f"[ONNX] Warmup failed for '{model_key}': {e}")
            return False

    def clear(self) -> None:
        """Flushes all cached sessions from memory and VRAM."""
        with self._lock:
            self._sessions.clear()
            self._session_providers.clear()


# Global Singleton
_onnx_manager: Optional[ONNXRuntimeManager] = None


def get_onnx_manager() -> ONNXRuntimeManager:
    """Access global ONNXRuntimeManager singleton."""
    global _onnx_manager
    if _onnx_manager is None:
        _onnx_manager = ONNXRuntimeManager()
    return _onnx_manager
