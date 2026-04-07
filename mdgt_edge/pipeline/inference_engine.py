"""Inference backends for the MDGTv2 fingerprint embedding model.

Supports ONNX Runtime and TensorRT with graceful fallback when either
dependency is unavailable.
"""

from __future__ import annotations

import logging
import os
import select
import struct
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np

from mdgt_edge.pipeline.graph_builder import GraphData

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Abstract base
# ------------------------------------------------------------------


class InferenceBackend(ABC):
    """Interface for MDGTv2 model inference backends."""

    @abstractmethod
    def load(self, model_path: str) -> bool:
        """Load a serialised model.

        Args:
            model_path: Filesystem path to the model file.

        Returns:
            ``True`` if the model was loaded successfully.
        """

    @abstractmethod
    def infer(self, graph_data: GraphData) -> np.ndarray:
        """Run inference and return a 256-dim L2-normalised embedding.

        Args:
            graph_data: Graph representation of a minutiae set.

        Returns:
            1-D float32 ndarray of length 256.
        """

    def infer_image(self, image_tensor: np.ndarray) -> np.ndarray:
        """Run inference on a preprocessed image tensor.

        Args:
            image_tensor: Float32 NCHW tensor of shape (1, 3, H, W).

        Returns:
            1-D float32 ndarray of length 256.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support image-based inference."
        )

    @abstractmethod
    def get_info(self) -> dict[str, Any]:
        """Return model / backend metadata."""

    # Shared helpers -----------------------------------------------

    @staticmethod
    def _l2_normalize(vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        if norm < 1e-12:
            return vec
        return vec / norm

    def warmup(self, graph_data: GraphData, iterations: int = 5) -> float:
        """Run *iterations* dummy inferences and return average latency (ms).

        Args:
            graph_data: A representative graph for warm-up.
            iterations: Number of warm-up passes.

        Returns:
            Average inference time in milliseconds.
        """
        total = 0.0
        for _ in range(iterations):
            t0 = time.perf_counter()
            self.infer(graph_data)
            total += (time.perf_counter() - t0) * 1000.0
        avg = total / max(iterations, 1)
        logger.info(
            "%s warmup: %d iters, avg %.2f ms",
            self.__class__.__name__,
            iterations,
            avg,
        )
        return avg

    def profile(self, graph_data: GraphData, iterations: int = 20) -> dict[str, float]:
        """Profile inference latency over *iterations* runs.

        Returns:
            Dict with ``avg_ms``, ``min_ms``, ``max_ms``, ``p95_ms``.
        """
        latencies: list[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            self.infer(graph_data)
            latencies.append((time.perf_counter() - t0) * 1000.0)
        latencies.sort()
        count = len(latencies)
        p95_idx = min(int(count * 0.95), count - 1)
        return {
            "avg_ms": sum(latencies) / count,
            "min_ms": latencies[0],
            "max_ms": latencies[-1],
            "p95_ms": latencies[p95_idx],
        }


# ------------------------------------------------------------------
# ONNX Runtime backend
# ------------------------------------------------------------------


class ONNXBackend(InferenceBackend):
    """ONNX Runtime inference backend with dynamic-shape support."""

    def __init__(self) -> None:
        self._session = None
        self._model_path: str | None = None
        self._ort = None

    def load(self, model_path: str) -> bool:
        try:
            import onnxruntime as ort

            self._ort = ort
        except ImportError:
            logger.error("onnxruntime is not installed.")
            return False

        try:
            sess_opts = ort.SessionOptions()
            sess_opts.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            providers = []
            available = ort.get_available_providers()
            if "CUDAExecutionProvider" in available:
                providers.append("CUDAExecutionProvider")
            providers.append("CPUExecutionProvider")

            self._session = ort.InferenceSession(
                model_path, sess_options=sess_opts, providers=providers
            )
            self._model_path = model_path
            logger.info("ONNX model loaded from %s (providers=%s)", model_path, providers)
            return True
        except Exception as exc:
            logger.error("Failed to load ONNX model %s: %s", model_path, exc)
            return False

    def infer(self, graph_data: GraphData) -> np.ndarray:
        if self._session is None:
            raise RuntimeError("ONNX model not loaded. Call load() first.")

        # Build feed dict matching expected dynamic-axis inputs
        node_feat = graph_data.node_features.astype(np.float32)
        edge_idx = graph_data.edge_index.astype(np.int64)
        rel_feat = graph_data.relational_features.astype(np.float32)

        # Add batch dim if model expects it
        if node_feat.ndim == 2:
            node_feat = node_feat[np.newaxis, ...]  # (1, N, 5)
        if edge_idx.ndim == 2:
            edge_idx = edge_idx[np.newaxis, ...]  # (1, N, k)
        if rel_feat.ndim == 3:
            rel_feat = rel_feat[np.newaxis, ...]  # (1, N, N, 7)

        input_names = [inp.name for inp in self._session.get_inputs()]
        feed: dict[str, np.ndarray] = {}

        # Map positionally -- the ONNX export order is:
        #   node_features, edge_index, relational_features
        inputs_data = [node_feat, edge_idx, rel_feat]
        for name, data in zip(input_names, inputs_data):
            feed[name] = data

        outputs = self._session.run(None, feed)
        embedding = outputs[0].squeeze().astype(np.float32)

        return self._l2_normalize(embedding)

    def infer_image(self, image_tensor: np.ndarray) -> np.ndarray:
        if self._session is None:
            raise RuntimeError("ONNX model not loaded. Call load() first.")

        image = np.ascontiguousarray(image_tensor.astype(np.float32))
        input_name = self._session.get_inputs()[0].name
        outputs = self._session.run(None, {input_name: image})
        embedding = outputs[0].squeeze().astype(np.float32)
        return self._l2_normalize(embedding)

    def get_info(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "backend": "onnxruntime",
            "model_path": self._model_path,
            "loaded": self._session is not None,
        }
        if self._session is not None:
            info["inputs"] = [
                {"name": i.name, "shape": i.shape, "type": i.type}
                for i in self._session.get_inputs()
            ]
            info["outputs"] = [
                {"name": o.name, "shape": o.shape, "type": o.type}
                for o in self._session.get_outputs()
            ]
        return info


# ------------------------------------------------------------------
# TensorRT backend (ctypes fallback)
# ------------------------------------------------------------------


class TRTCtypesBackend(InferenceBackend):
    """TensorRT backend using ctypes for CUDA memory management.

    Works on Jetson Nano without pycuda. Only supports image-based inference
    (ViT model with input shape [1, 3, 224, 224]).
    """

    def __init__(self) -> None:
        self._engine = None
        self._context = None
        self._model_path: str | None = None
        self._trt = None
        self._libcudart = None
        self._d_input = None
        self._d_output = None
        self._input_size: int = 0
        self._output_size: int = 0
        self._output_shape: tuple = ()

    def load(self, model_path: str) -> bool:
        try:
            import tensorrt as trt
            self._trt = trt
        except ImportError:
            logger.error("tensorrt not available.")
            return False

        try:
            import ctypes
            self._libcudart = ctypes.CDLL("libcudart.so")
        except OSError:
            logger.error("libcudart.so not found.")
            return False

        try:
            trt_logger = trt.Logger(trt.Logger.WARNING)
            runtime = trt.Runtime(trt_logger)

            with open(model_path, "rb") as f:
                self._engine = runtime.deserialize_cuda_engine(f.read())

            if self._engine is None:
                logger.error("Failed to deserialise TRT engine from %s", model_path)
                return False

            self._context = self._engine.create_execution_context()
            self._model_path = model_path

            # Pre-allocate GPU buffers
            import ctypes as ct
            for i in range(self._engine.num_bindings):
                shape = self._engine.get_binding_shape(i)
                dtype = trt.nptype(self._engine.get_binding_dtype(i))
                size = int(np.prod(shape)) * np.dtype(dtype).itemsize

                if self._engine.binding_is_input(i):
                    self._input_size = size
                    self._d_input = ct.c_void_p()
                    self._libcudart.cudaMalloc(ct.byref(self._d_input), ct.c_size_t(size))
                else:
                    self._output_size = size
                    self._output_shape = tuple(shape)
                    self._d_output = ct.c_void_p()
                    self._libcudart.cudaMalloc(ct.byref(self._d_output), ct.c_size_t(size))

            logger.info("TRT engine loaded (ctypes): %s", model_path)
            return True
        except Exception as exc:
            logger.error("TRT load failed for %s: %s", model_path, exc)
            return False

    def infer(self, graph_data: GraphData) -> np.ndarray:
        raise NotImplementedError("TRTCtypesBackend only supports infer_image().")

    def infer_image(self, image_tensor: np.ndarray) -> np.ndarray:
        if self._engine is None or self._context is None:
            raise RuntimeError("TRT engine not loaded. Call load() first.")

        import ctypes as ct

        input_data = np.ascontiguousarray(image_tensor.astype(np.float32))

        # H2D
        self._libcudart.cudaMemcpy(
            self._d_input, input_data.ctypes.data,
            ct.c_size_t(self._input_size), ct.c_int(1),
        )

        # Execute
        bindings = [int(self._d_input.value), int(self._d_output.value)]
        self._context.execute_v2(bindings)

        # D2H
        output = np.empty(self._output_shape, dtype=np.float32)
        self._libcudart.cudaMemcpy(
            output.ctypes.data, self._d_output,
            ct.c_size_t(self._output_size), ct.c_int(2),
        )

        embedding = output.squeeze().astype(np.float32)
        return self._l2_normalize(embedding)

    def get_info(self) -> dict[str, Any]:
        return {
            "backend": "tensorrt-ctypes",
            "model_path": self._model_path,
            "loaded": self._engine is not None,
        }

    def __del__(self) -> None:
        if self._libcudart is not None:
            if self._d_input is not None:
                self._libcudart.cudaFree(self._d_input)
            if self._d_output is not None:
                self._libcudart.cudaFree(self._d_output)


# ------------------------------------------------------------------
# TensorRT backend (pycuda)
# ------------------------------------------------------------------


class TensorRTBackend(InferenceBackend):
    """TensorRT inference backend optimised for Jetson Nano FP16.

    Falls back gracefully when ``tensorrt`` is not importable.
    """

    def __init__(self) -> None:
        self._engine = None
        self._context = None
        self._model_path: str | None = None
        self._trt = None
        self._cuda = None
        self._bindings: list[dict[str, Any]] = []
        self._stream = None

    def load(self, model_path: str) -> bool:
        try:
            import tensorrt as trt  # type: ignore[import-untyped]
            import pycuda.driver as cuda  # type: ignore[import-untyped]
            import pycuda.autoinit  # type: ignore[import-untyped]  # noqa: F401

            self._trt = trt
            self._cuda = cuda
        except ImportError as exc:
            logger.error(
                "TensorRT or PyCUDA not available: %s. "
                "Use ONNXBackend as a fallback.",
                exc,
            )
            return False

        trt_logger = self._trt.Logger(self._trt.Logger.WARNING)

        try:
            with open(model_path, "rb") as f:
                engine_data = f.read()

            runtime = self._trt.Runtime(trt_logger)
            self._engine = runtime.deserialize_cuda_engine(engine_data)
            if self._engine is None:
                logger.error("Failed to deserialise TensorRT engine from %s", model_path)
                return False

            self._context = self._engine.create_execution_context()
            self._stream = self._cuda.Stream()
            self._model_path = model_path

            # Pre-allocate bindings
            self._bindings = []
            for i in range(self._engine.num_bindings):
                name = self._engine.get_binding_name(i)
                dtype = self._trt.nptype(self._engine.get_binding_dtype(i))
                shape = self._engine.get_binding_shape(i)
                is_input = self._engine.binding_is_input(i)
                self._bindings.append(
                    {
                        "name": name,
                        "dtype": dtype,
                        "shape": tuple(shape),
                        "is_input": is_input,
                        "index": i,
                    }
                )

            logger.info(
                "TensorRT engine loaded from %s (%d bindings)",
                model_path,
                len(self._bindings),
            )
            return True
        except Exception as exc:
            logger.error("TensorRT load failed for %s: %s", model_path, exc)
            return False

    def infer(self, graph_data: GraphData) -> np.ndarray:
        if self._engine is None or self._context is None:
            raise RuntimeError("TensorRT engine not loaded. Call load() first.")

        cuda = self._cuda
        n = graph_data.num_nodes
        k = graph_data.edge_index.shape[1] if graph_data.edge_index.ndim == 2 else 0

        # Prepare host buffers and set dynamic shapes
        host_inputs: list[np.ndarray] = []
        host_outputs: list[np.ndarray] = []
        device_buffers: list[Any] = []
        buffer_ptrs: list[int] = []

        input_data_map = {
            0: graph_data.node_features.astype(np.float32),
            1: graph_data.edge_index.astype(np.int32),
            2: graph_data.relational_features.astype(np.float32),
        }

        input_idx = 0
        for binding in self._bindings:
            if binding["is_input"]:
                data = input_data_map.get(input_idx)
                if data is None:
                    raise RuntimeError(
                        f"No input data for binding index {input_idx}"
                    )
                # Add batch dim
                if data.ndim < len(binding["shape"]):
                    data = data[np.newaxis, ...]
                # Set dynamic shape
                self._context.set_binding_shape(binding["index"], data.shape)
                host_buf = np.ascontiguousarray(data)
                host_inputs.append(host_buf)
                dev_buf = cuda.mem_alloc(host_buf.nbytes)
                device_buffers.append(dev_buf)
                buffer_ptrs.append(int(dev_buf))
                input_idx += 1
            else:
                shape = tuple(
                    self._context.get_binding_shape(binding["index"])
                )
                host_buf = np.empty(shape, dtype=binding["dtype"])
                host_outputs.append(host_buf)
                dev_buf = cuda.mem_alloc(host_buf.nbytes)
                device_buffers.append(dev_buf)
                buffer_ptrs.append(int(dev_buf))

        # H2D transfer
        for h_in, d_buf in zip(host_inputs, device_buffers[: len(host_inputs)]):
            cuda.memcpy_htod_async(d_buf, h_in, self._stream)

        # Execute
        self._context.execute_async_v2(
            bindings=buffer_ptrs, stream_handle=self._stream.handle
        )

        # D2H transfer
        out_offset = len(host_inputs)
        for h_out, d_buf in zip(
            host_outputs, device_buffers[out_offset:]
        ):
            cuda.memcpy_dtoh_async(h_out, d_buf, self._stream)

        self._stream.synchronize()

        embedding = host_outputs[0].squeeze().astype(np.float32)
        return self._l2_normalize(embedding)

    def get_info(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "backend": "tensorrt",
            "model_path": self._model_path,
            "loaded": self._engine is not None,
        }
        if self._bindings:
            info["bindings"] = [
                {
                    "name": b["name"],
                    "shape": b["shape"],
                    "is_input": b["is_input"],
                }
                for b in self._bindings
            ]
        return info


# ------------------------------------------------------------------
# TensorRT subprocess backend (Python 3.6 worker)
# ------------------------------------------------------------------


class TRTSubprocessBackend(InferenceBackend):
    """TensorRT backend via a system Python 3.6 subprocess.

    The Jetson Nano's TensorRT Python bindings are compiled for cpython-36
    and cannot be loaded in Python 3.9+.  This backend spawns a worker
    process under ``/usr/bin/python3`` (system 3.6) that handles TRT
    inference, communicating via a binary stdin/stdout pipe.
    """

    # Path to the worker script relative to the project root
    _WORKER_SCRIPT = "tools/trt_worker.py"
    _SYSTEM_PYTHON = "/usr/bin/python3"
    _INFER_TIMEOUT = 10.0  # seconds per inference call

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._model_path: str | None = None
        self._lock = threading.Lock()

    def load(self, model_path: str) -> bool:
        # Locate trt_worker.py relative to this file or the project root
        worker = self._find_worker_script()
        if worker is None:
            logger.error("trt_worker.py not found.")
            return False

        if not os.path.exists(self._SYSTEM_PYTHON):
            logger.error("System python not found at %s", self._SYSTEM_PYTHON)
            return False

        try:
            self._proc = subprocess.Popen(
                [self._SYSTEM_PYTHON, worker, model_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )

            # Wait for the "ready" signal on stderr (up to 30s)
            import select
            ready = False
            deadline = time.monotonic() + 30.0
            stderr_lines: list[str] = []
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                r, _, _ = select.select([self._proc.stderr], [], [], min(remaining, 1.0))
                if r:
                    line = self._proc.stderr.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="replace").strip()
                    stderr_lines.append(text)
                    logger.info("trt_worker: %s", text)
                    if "trt_worker ready" in text:
                        ready = True
                        break
                # Check if process died
                if self._proc.poll() is not None:
                    break

            if not ready:
                logger.error(
                    "trt_worker failed to start. stderr: %s",
                    "; ".join(stderr_lines),
                )
                self._cleanup()
                return False

            self._model_path = model_path
            logger.info("TRTSubprocessBackend loaded: %s", model_path)
            return True
        except Exception as exc:
            logger.error("TRTSubprocessBackend load failed: %s", exc)
            self._cleanup()
            return False

    def infer(self, graph_data: GraphData) -> np.ndarray:
        raise NotImplementedError("TRTSubprocessBackend only supports infer_image().")

    def infer_image(self, image_tensor: np.ndarray) -> np.ndarray:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                raise RuntimeError("TRT worker process not running.")

            data = np.ascontiguousarray(image_tensor.astype(np.float32)).tobytes()

            try:
                # Send: 4-byte LE length + data
                self._proc.stdin.write(struct.pack("<I", len(data)))
                self._proc.stdin.write(data)
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._cleanup()
                raise RuntimeError(f"TRT worker pipe broken on write: {exc}")

            # Receive: 4-byte LE length + embedding bytes
            hdr = self._read_exact(self._proc.stdout, 4, self._INFER_TIMEOUT)
            if hdr is None or len(hdr) < 4:
                self._cleanup()
                raise RuntimeError("TRT worker: failed to read response header (timeout or dead).")
            resp_len = struct.unpack("<I", hdr)[0]

            resp_data = self._read_exact(self._proc.stdout, resp_len, self._INFER_TIMEOUT)
            if resp_data is None or len(resp_data) < resp_len:
                self._cleanup()
                raise RuntimeError("TRT worker: incomplete response.")

            embedding = np.frombuffer(resp_data, dtype=np.float32)
            return self._l2_normalize(embedding)

    def get_info(self) -> dict[str, Any]:
        running = self._proc is not None and self._proc.poll() is None
        return {
            "backend": "tensorrt-subprocess",
            "model_path": self._model_path,
            "loaded": running,
        }

    def shutdown(self) -> None:
        """Gracefully stop the worker process."""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                try:
                    self._proc.stdin.write(struct.pack("<I", 0))
                    self._proc.stdin.flush()
                    self._proc.wait(timeout=5)
                except Exception:
                    self._proc.kill()
            self._proc = None

    def __del__(self) -> None:
        self.shutdown()

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _read_exact(stream, n: int, timeout: float = 10.0) -> bytes | None:
        """Read exactly *n* bytes from a binary stream with timeout."""
        result: list[bytes | None] = [None]

        def _reader() -> None:
            buf = b""
            while len(buf) < n:
                chunk = stream.read(n - len(buf))
                if not chunk:
                    result[0] = None
                    return
                buf += chunk
            result[0] = buf

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            logger.error("_read_exact: timeout after %.1fs reading %d bytes", timeout, n)
            return None
        return result[0]

    def _find_worker_script(self) -> str | None:
        """Locate trt_worker.py in several candidate locations."""
        candidates = [
            # Relative to project root (when running from project dir)
            Path(self._WORKER_SCRIPT),
            # Relative to this file
            Path(__file__).resolve().parent.parent.parent / self._WORKER_SCRIPT,
            # Absolute fallback on Jetson
            Path("/home/binhan2/jetson-fingerverify-app") / self._WORKER_SCRIPT,
        ]
        for p in candidates:
            if p.exists():
                return str(p)
        return None

    def _cleanup(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
            self._proc = None
