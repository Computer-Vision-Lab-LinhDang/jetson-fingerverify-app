#!/usr/bin/env python3
"""TRT inference worker — runs under system Python 3.6 with tensorrt.

Protocol (stdin/stdout, binary):
  Request:  4 bytes (int32 LE) data length + raw float32 tensor bytes
  Response: 4 bytes (int32 LE) data length + raw float32 embedding bytes
  Special:  length=0 means shutdown

Launched by TRTSubprocessBackend from the main Python 3.9 process.
"""
import os
import struct
import sys
import ctypes
import numpy as np

# Save the real binary stdout fd BEFORE anything can write to it.
_stdout_fd = os.dup(1)  # dup original fd 1
_stdout_bin = os.fdopen(_stdout_fd, "wb", buffering=0)

# Redirect fd 1 -> fd 2 (stderr) so C-level TRT warnings don't pollute the pipe.
os.dup2(2, 1)
sys.stdout = sys.stderr


def main():
    import tensorrt as trt

    if len(sys.argv) < 2:
        sys.stderr.write("Usage: trt_worker.py <engine_path>\n")
        sys.exit(1)

    engine_path = sys.argv[1]

    # Load engine
    logger = trt.Logger(trt.Logger.WARNING)
    runtime = trt.Runtime(logger)
    with open(engine_path, "rb") as f:
        engine = runtime.deserialize_cuda_engine(f.read())
    if engine is None:
        sys.stderr.write("Failed to load engine: {}\n".format(engine_path))
        sys.exit(1)

    context = engine.create_execution_context()

    # Pre-allocate GPU buffers via ctypes
    libcudart = ctypes.CDLL("libcudart.so")

    input_shape = tuple(engine.get_binding_shape(0))   # (1,3,224,224)
    output_shape = tuple(engine.get_binding_shape(1))   # (1,256)

    input_size = int(np.prod(input_shape)) * 4   # float32
    output_size = int(np.prod(output_shape)) * 4

    d_input = ctypes.c_void_p()
    d_output = ctypes.c_void_p()
    libcudart.cudaMalloc(ctypes.byref(d_input), ctypes.c_size_t(input_size))
    libcudart.cudaMalloc(ctypes.byref(d_output), ctypes.c_size_t(output_size))

    # Signal ready
    sys.stderr.write("trt_worker ready: {}\n".format(engine_path))
    sys.stderr.flush()

    stdin = sys.stdin.buffer
    stdout = _stdout_bin  # clean binary pipe, no TRT warnings

    while True:
        # Read request length
        hdr = stdin.read(4)
        if len(hdr) < 4:
            break
        data_len = struct.unpack("<I", hdr)[0]
        if data_len == 0:
            break  # shutdown

        # Read tensor data
        data = stdin.read(data_len)
        if len(data) < data_len:
            break

        input_arr = np.frombuffer(data, dtype=np.float32).reshape(input_shape)
        input_arr = np.ascontiguousarray(input_arr)

        # H2D
        libcudart.cudaMemcpy(
            d_input, input_arr.ctypes.data,
            ctypes.c_size_t(input_size), ctypes.c_int(1)
        )

        # Execute
        bindings = [int(d_input.value), int(d_output.value)]
        context.execute_v2(bindings)

        # D2H
        output_arr = np.empty(output_shape, dtype=np.float32)
        libcudart.cudaMemcpy(
            output_arr.ctypes.data, d_output,
            ctypes.c_size_t(output_size), ctypes.c_int(2)
        )

        # L2 normalize
        emb = output_arr.squeeze().astype(np.float32)
        norm = np.linalg.norm(emb)
        if norm > 1e-12:
            emb = emb / norm

        # Send response
        emb_bytes = emb.tobytes()
        stdout.write(struct.pack("<I", len(emb_bytes)))
        stdout.write(emb_bytes)
        stdout.flush()

    # Cleanup
    libcudart.cudaFree(d_input)
    libcudart.cudaFree(d_output)


if __name__ == "__main__":
    main()
