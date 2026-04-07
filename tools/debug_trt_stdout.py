#!/usr/bin/env python3
"""Debug: check if TRT worker leaks data to stdout during init."""
import subprocess
import select
import os
import struct
import time
import numpy as np

PYTHON = "/usr/bin/python3"
WORKER = "/home/binhan2/jetson-fingerverify-app/tools/trt_worker.py"
ENGINE = "/home/binhan2/jetson-fingerverify-app/models/model_fp16.engine"

print("Spawning trt_worker...")
proc = subprocess.Popen(
    [PYTHON, WORKER, ENGINE],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    bufsize=0,
)

# Wait for ready on stderr
for _ in range(30):
    r, _, _ = select.select([proc.stderr], [], [], 1.0)
    if r:
        line = proc.stderr.readline().decode().strip()
        print("stderr:", line)
        if "ready" in line:
            break

# Check if there's any stale data on stdout
time.sleep(0.5)
r, _, _ = select.select([proc.stdout], [], [], 0.5)
if r:
    stale = os.read(proc.stdout.fileno(), 4096)
    print("STALE stdout: {} bytes".format(len(stale)))
    print("  hex:", stale[:80].hex())
    print("  repr:", repr(stale[:80]))
else:
    print("stdout CLEAN - no stale data")

# Now send a real tensor and try to read response
print("\nSending tensor...")
tensor = np.random.randn(1, 3, 224, 224).astype(np.float32)
data = tensor.tobytes()
proc.stdin.write(struct.pack("<I", len(data)))
proc.stdin.write(data)
proc.stdin.flush()

# Read 4-byte header with select
print("Reading header...")
time.sleep(0.3)
r, _, _ = select.select([proc.stdout], [], [], 5.0)
if r:
    hdr_raw = os.read(proc.stdout.fileno(), 4)
    print("  hdr raw hex:", hdr_raw.hex())
    print("  hdr raw repr:", repr(hdr_raw))
    if len(hdr_raw) == 4:
        resp_len = struct.unpack("<I", hdr_raw)[0]
        print("  resp_len:", resp_len)
        if resp_len < 100000:
            # Read the rest
            buf = b""
            while len(buf) < resp_len:
                chunk = os.read(proc.stdout.fileno(), resp_len - len(buf))
                if not chunk:
                    break
                buf += chunk
            emb = np.frombuffer(buf, dtype=np.float32)
            print("  emb shape:", emb.shape, "norm:", np.linalg.norm(emb))
        else:
            print("  ERROR: resp_len too large, reading more raw bytes...")
            more = os.read(proc.stdout.fileno(), 256)
            print("  more hex:", more[:80].hex())
else:
    print("  no data on stdout after 5s!")

# Shutdown
proc.stdin.write(struct.pack("<I", 0))
proc.stdin.flush()
try:
    proc.wait(timeout=3)
except:
    proc.kill()
print("Done")
