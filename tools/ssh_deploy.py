#!/usr/bin/env python3
"""Deploy & setup MDGT Edge on Jetson Nano via SSH."""
import paramiko
import sys
import time

HOST = "100.92.102.86"
USER = "binhan2"
PASS = "Anbinh@93"
PROJECT = "/home/binhan2/jetson-fingerverify-app"

def run(ssh, cmd, timeout=120, show=True):
    if show:
        print(f"  $ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    code = stdout.channel.recv_exit_status()
    if show and out:
        for line in out.split('\n')[:20]:
            print(f"    {line}")
        if out.count('\n') > 20:
            print(f"    ... ({out.count(chr(10))+1} lines)")
    if code != 0 and err:
        print(f"    [ERR {code}] {err[:300]}")
    return out, err, code

def run_sudo(ssh, cmd, timeout=120, show=True):
    """Run command with sudo using password."""
    full_cmd = f"echo '{PASS}' | sudo -S {cmd}"
    return run(ssh, full_cmd, timeout=timeout, show=show)

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASS, timeout=10)
    print(f"SSH connected to {USER}@{HOST}\n")

    # ---------------------------------------------------------------
    # Step 1: Sync latest code from local to Jetson
    # ---------------------------------------------------------------
    print("=== Step 1: Sync code ===")
    print("  (Handled via git push/pull — skipping rsync for now)")
    run(ssh, f"cd {PROJECT} && git pull 2>&1 || echo 'git pull skipped'")

    # ---------------------------------------------------------------
    # Step 2: Install system deps
    # ---------------------------------------------------------------
    print("\n=== Step 2: Install system packages ===")

    # Check python version
    out, _, _ = run(ssh, "python3 --version")

    # Install pip if missing
    run(ssh, "which pip3 || (curl -sS https://bootstrap.pypa.io/pip/3.6/get-pip.py | python3)", timeout=60)

    # Install pyusb
    print("\n  Installing pyusb...")
    run(ssh, "pip3 install --user pyusb 2>&1 | tail -3", timeout=60)

    # Install other core deps
    print("\n  Installing core Python deps...")
    run(ssh, "pip3 install --user pyyaml click numpy pillow 2>&1 | tail -5", timeout=120)

    # Verify pyusb
    out, err, code = run(ssh, "python3 -c 'import usb.core; print(\"pyusb OK\")'")
    if code != 0:
        print(f"    WARNING: pyusb still not working: {err[:200]}")

    # ---------------------------------------------------------------
    # Step 3: Copy fingerprint SDK if not present
    # ---------------------------------------------------------------
    print("\n=== Step 3: Fingerprint SDK ===")
    out, _, _ = run(ssh, f"ls {PROJECT}/fingerprint.py 2>/dev/null || ls /home/binhan2/fingerprint.py 2>/dev/null")
    if not out:
        # Check if we have it locally to SCP
        print("  SDK not found on Jetson. Checking local...")
        import os
        local_sdk = os.path.expanduser("~/Workspace/fingersensor/fingerprint.py")
        if os.path.exists(local_sdk):
            print(f"  Uploading {local_sdk} -> {PROJECT}/fingerprint.py")
            sftp = ssh.open_sftp()
            sftp.put(local_sdk, f"{PROJECT}/fingerprint.py")
            sftp.close()
            print("  SDK uploaded!")
        else:
            print(f"  WARNING: SDK not found locally at {local_sdk}")
            print("  You need to manually copy fingerprint.py to the Jetson")
    else:
        print(f"  SDK found: {out}")

    # ---------------------------------------------------------------
    # Step 4: USB udev rules for sensor access without sudo
    # ---------------------------------------------------------------
    print("\n=== Step 4: USB udev rules ===")
    out, _, _ = run(ssh, "cat /etc/udev/rules.d/99-fingerprint.rules 2>/dev/null")
    if "0483" not in (out or ""):
        print("  Creating udev rule for sensor (0483:5720)...")
        rule = 'SUBSYSTEM==\"usb\", ATTR{idVendor}==\"0483\", ATTR{idProduct}==\"5720\", MODE=\"0666\", GROUP=\"plugdev\"'
        run_sudo(ssh, f"bash -c 'echo {repr(rule)} > /etc/udev/rules.d/99-fingerprint.rules'")
        run_sudo(ssh, "udevadm control --reload-rules && udevadm trigger")
        print("  Udev rules applied. Sensor should be accessible without sudo.")
    else:
        print(f"  Udev rule already exists: {out}")

    # ---------------------------------------------------------------
    # Step 5: Initialize SQLite database
    # ---------------------------------------------------------------
    print("\n=== Step 5: Initialize Database ===")
    out, _, _ = run(ssh, f"ls -la {PROJECT}/data/mdgt_edge.db 2>/dev/null")
    print(f"  Existing DB: {out}" if out else "  No existing DB")

    # Run init via Python
    init_script = f"""
import sys
sys.path.insert(0, '{PROJECT}')
from mdgt_edge.database import DatabaseManager, UserRepository, FingerprintRepository, ConfigRepository, DeviceRepository
from mdgt_edge.database.models import Device

db = DatabaseManager('{PROJECT}/data/mdgt_edge.db')

# Check current state
ur = UserRepository(db)
fr = FingerprintRepository(db)
cr = ConfigRepository(db)

print(f"Users: {{ur.count()}}")
print(f"Fingerprints: {{fr.count()}}")

# Set default config if empty
if cr.count() == 0:
    defaults = {{
        "verify_threshold": "0.55",
        "identify_threshold": "0.50",
        "identify_top_k": "5",
        "min_quality_enroll": "40",
        "min_minutiae_count": "12",
        "max_failed_attempts": "3",
        "cooldown_seconds": "30",
        "knn_k": "16",
        "faiss_nprobe": "8",
        "model_path": "models/mdgtv2_fp16.engine",
    }}
    for k, v in defaults.items():
        cr.set(k, v)
    print(f"Config: {{len(defaults)}} defaults set")
else:
    print(f"Config: {{cr.count()}} entries")

# Register device
dr = DeviceRepository(db)
if dr.get_by_id("JETSON-001") is None:
    dr.create(Device(id="JETSON-001", name="Jetson Nano", location="Lab"))
    print("Device JETSON-001 registered")
else:
    print("Device JETSON-001 already registered")

print("Database OK!")
"""
    out, err, code = run(ssh, f"python3 -c {repr(init_script)}")
    if code != 0:
        print(f"    DB init error: {err[:500]}")

    # ---------------------------------------------------------------
    # Step 6: Test sensor
    # ---------------------------------------------------------------
    print("\n=== Step 6: Test Sensor ===")
    sensor_test = f"""
import sys
sys.path.insert(0, '{PROJECT}')
try:
    from fingerprint import FingerprintReader
    fp = FingerprintReader()
    if fp.open():
        count = fp.get_user_count()
        level = fp.get_compare_level()
        img = fp.capture_image()
        img_len = len(img) if img else 0
        print(f"SENSOR OK: users={{count}}, level={{level}}, capture={{img_len}} bytes")
        if img and img_len == 192*192:
            quality = sum(img) / len(img)
            std = (sum((x - quality)**2 for x in img) / len(img)) ** 0.5
            print(f"Image: 192x192, avg={{quality:.1f}}, std={{std:.1f}}")
        fp.close()
    else:
        print("SENSOR: open() failed")
except ImportError as e:
    print(f"IMPORT ERROR: {{e}}")
    print("Make sure fingerprint.py is in the project directory")
except Exception as e:
    print(f"ERROR: {{e}}")
"""
    out, err, code = run(ssh, f"python3 -c {repr(sensor_test)}")
    if code != 0 and err:
        print(f"    Sensor test error: {err[:300]}")

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n=== Summary ===")
    run(ssh, f"python3 -c 'import usb.core; print(\"pyusb: OK\")' 2>&1 || echo 'pyusb: FAILED'")
    run(ssh, f"ls {PROJECT}/fingerprint.py 2>/dev/null && echo 'SDK: OK' || echo 'SDK: MISSING'")
    run(ssh, f"ls {PROJECT}/data/mdgt_edge.db 2>/dev/null && echo 'Database: OK' || echo 'Database: MISSING'")
    run(ssh, "lsusb | grep 0483 && echo 'Sensor USB: CONNECTED' || echo 'Sensor USB: NOT FOUND'")

    ssh.close()
    print("\nDone!")

if __name__ == "__main__":
    main()
