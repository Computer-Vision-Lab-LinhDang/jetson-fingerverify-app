#!/usr/bin/env python3
"""Quick test for the TRT subprocess worker."""
import sys
import struct
import subprocess
import time
import select
import numpy as np

WORKER = "/home/binhan2/jetson-fingerverify-app/tools/trt_worker.py"
ENGINE = "/home/binhan2/jetson-fingerverify-app/models/model_fp16.engine"
PYTHON = "/usr/bin/python3"

print("Starting trt_worker...")
proc = subprocess.Popen(
    [PYTHON, WORKER, ENGINE],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0
)

# Wait for ready
deadline = time.monotonic() + 30
ready = False
while time.monotonic() < deadline:
    r, _, _ = select.select([proc.stderr], [], [], 1.0)
    if r:
        line = proc.stderr.readline().decode().strip()
        print("stderr:", line)
        if "ready" in line:
            ready = True
            break
    if proc.poll() is not None:
        print("Worker died!")
        remaining = proc.stderr.read().decode()
        print("remaining stderr:", remaining)
        sys.exit(1)

if not ready:
    print("Worker not ready after 30s")
    proc.kill()
    sys.exit(1)

# Send dummy tensor (1,3,224,224)
tensor = np.random.randn(1, 3, 224, 224).astype(np.float32)
data = tensor.tobytes()
print("Sending tensor: {} bytes".format(len(data)))

t0 = time.time()
proc.stdin.write(struct.pack("<I", len(data)))
proc.stdin.write(data)
proc.stdin.flush()

# Read response
hdr = proc.stdout.read(4)
resp_len = struct.unpack("<I", hdr)[0]
resp = proc.stdout.read(resp_len)
elapsed = (time.time() - t0) * 1000

emb = np.frombuffer(resp, dtype=np.float32)
print("Embedding shape: {}, norm: {:.4f}, latency: {:.1f}ms".format(
    emb.shape, np.linalg.norm(emb), elapsed
))

# Run a few more to measure steady-state
latencies = []
for i in range(5):
    tensor = np.random.randn(1, 3, 224, 224).astype(np.float32)
    data = tensor.tobytes()
    t0 = time.time()
    proc.stdin.write(struct.pack("<I", len(data)))
    proc.stdin.write(data)
    proc.stdin.flush()
    hdr = proc.stdout.read(4)
    resp_len = struct.unpack("<I", hdr)[0]
    resp = proc.stdout.read(resp_len)
    lat = (time.time() - t0) * 1000
    latencies.append(lat)
    print("  iter {}: {:.1f}ms".format(i + 1, lat))

print("Avg latency: {:.1f}ms".format(sum(latencies) / len(latencies)))

# Shutdown
proc.stdin.write(struct.pack("<I", 0))
proc.stdin.flush()
proc.wait(timeout=5)
print("Worker exited OK")
