#!/usr/bin/env python3
"""Test TRTSubprocessBackend from conda Python 3.9 environment."""
import sys
import os
import time
import numpy as np

# Ensure project root is in path
sys.path.insert(0, "/home/binhan2/jetson-fingerverify-app")

from mdgt_edge.pipeline.inference_engine import TRTSubprocessBackend

ENGINE = "/home/binhan2/jetson-fingerverify-app/models/model_fp16.engine"

print("Testing TRTSubprocessBackend from Python", sys.version.split()[0])

backend = TRTSubprocessBackend()
ok = backend.load(ENGINE)
print("load ok:", ok)

if not ok:
    print("FAILED to load TRT subprocess backend")
    sys.exit(1)

# Single inference
tensor = np.random.randn(1, 3, 224, 224).astype(np.float32)
t0 = time.time()
emb = backend.infer_image(tensor)
elapsed = (time.time() - t0) * 1000
print("emb shape:", emb.shape, "norm: {:.4f}".format(np.linalg.norm(emb)),
      "latency: {:.1f}ms".format(elapsed))

# Multiple inferences
for i in range(3):
    tensor = np.random.randn(1, 3, 224, 224).astype(np.float32)
    t0 = time.time()
    emb = backend.infer_image(tensor)
    lat = (time.time() - t0) * 1000
    print("  iter {}: {:.1f}ms".format(i + 1, lat))

backend.shutdown()
print("SUCCESS - TRTSubprocessBackend works from conda Python 3.9!")
