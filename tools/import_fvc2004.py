#!/usr/bin/env python3
"""Import FVC2004 dataset into MDGT Edge database.

Each TIF sample = 1 user with 1 fingerprint.
Preprocesses image, runs ONNX inference for 256-dim embedding, saves to SQLite.
"""
import hashlib
import os
import re
import sys
import time

import cv2
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mdgt_edge.database.database import DatabaseManager
from mdgt_edge.database.models import Fingerprint, User, UserRole
from mdgt_edge.database.repository import FingerprintRepository, UserRepository
from mdgt_edge.pipeline.inference_engine import ONNXBackend

# --- Config ---
FVC_DIR = os.path.expanduser("~/jetson-nano-fingerpint/data/FVC2004")
MODEL_PATH = os.path.expanduser("~/jetson-fingerverify-app/models/model.onnx")
DB_PATH = "data/mdgt_edge.db"
IMAGES_DIR = os.path.expanduser("~/.mdgt_edge/images")
MODEL_SIZE = 224


def preprocess(gray: np.ndarray) -> np.ndarray:
    """Grayscale image -> (1, 3, 224, 224) float32 tensor."""
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    resized = cv2.resize(enhanced, (MODEL_SIZE, MODEL_SIZE), interpolation=cv2.INTER_LINEAR)
    rgb = np.stack([resized, resized, resized], axis=0).astype(np.float32) / 255.0
    return np.expand_dims(rgb, axis=0)


def save_image(fp_id: int, raw: bytes, width: int, height: int) -> None:
    """Save raw fingerprint image for identify visualization."""
    os.makedirs(IMAGES_DIR, exist_ok=True)
    with open(os.path.join(IMAGES_DIR, f"{fp_id}.raw"), "wb") as f:
        f.write(raw)
    with open(os.path.join(IMAGES_DIR, f"{fp_id}.meta"), "w") as f:
        f.write(f"{width},{height}")


def main() -> None:
    # Collect all TIF files
    all_files: list[tuple[str, str, int, int]] = []  # (path, db_name, person_id, sample_id)
    for db_name in sorted(os.listdir(FVC_DIR)):
        db_path = os.path.join(FVC_DIR, db_name)
        if not os.path.isdir(db_path):
            continue
        for fname in sorted(os.listdir(db_path)):
            m = re.match(r"(\d+)_(\d+)\.tif", fname)
            if not m:
                continue
            person_id = int(m.group(1))
            sample_id = int(m.group(2))
            all_files.append((os.path.join(db_path, fname), db_name, person_id, sample_id))

    print(f"Found {len(all_files)} TIF files")
    if not all_files:
        print("No files found. Check FVC_DIR:", FVC_DIR)
        return

    # Load ONNX model
    print(f"Loading ONNX model: {MODEL_PATH}")
    backend = ONNXBackend()
    if not backend.load(MODEL_PATH):
        print("Failed to load ONNX model")
        return
    print("Model loaded OK")

    # Init DB
    db = DatabaseManager(DB_PATH)
    user_repo = UserRepository(db)
    fp_repo = FingerprintRepository(db)

    # Import each sample as a separate user
    t0 = time.time()
    imported = 0
    errors = 0

    for i, (fpath, db_name, person_id, sample_id) in enumerate(all_files):
        emp_id = f"FVC-{db_name}-{person_id:03d}-{sample_id}"
        name = f"FVC {db_name} P{person_id} S{sample_id}"

        try:
            # Read TIF
            gray = cv2.imread(fpath, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                print(f"  SKIP {fpath}: cannot read")
                errors += 1
                continue

            h, w = gray.shape
            raw = gray.tobytes()
            img_hash = hashlib.sha256(raw).hexdigest()[:16]

            # Preprocess + infer
            tensor = preprocess(gray)
            embedding = backend.infer_image(tensor)
            emb_bytes = embedding.tobytes()

            # Create user
            user = user_repo.create(User(
                employee_id=emp_id,
                full_name=name,
                department=db_name,
                role=UserRole.USER,
            ))

            # Create fingerprint
            fp = fp_repo.create(Fingerprint(
                user_id=user.id,
                finger_index=0,
                embedding_enc=emb_bytes,
                quality_score=50.0,
                image_hash=img_hash,
            ))

            # Save image for visualization
            save_image(fp.id, raw, w, h)

            imported += 1
            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                rate = imported / elapsed
                print(f"  [{i+1}/{len(all_files)}] {imported} imported, {rate:.1f}/s")

        except Exception as exc:
            print(f"  ERROR {fpath}: {exc}")
            errors += 1

    elapsed = time.time() - t0
    print(f"\nDone: {imported} imported, {errors} errors, {elapsed:.1f}s ({imported/elapsed:.1f}/s)")
    print(f"DB: {user_repo.count()} users, {fp_repo.count()} fingerprints")


if __name__ == "__main__":
    main()
