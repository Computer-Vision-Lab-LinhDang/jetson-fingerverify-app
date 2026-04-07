#!/usr/bin/env python3
"""Quick SSH test to check sensor on Jetson."""
import paramiko
import sys

HOST = "100.92.102.86"
USER = "binhan2"
PASS = "Anbinh@93"

def run(ssh, cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    return stdout.read().decode().strip(), stderr.read().decode().strip()

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(HOST, username=USER, password=PASS, timeout=10)
    except Exception as e:
        print(f"SSH connection failed: {e}")
        sys.exit(1)
    print(f"SSH connected to {USER}@{HOST}")

    # 1. USB devices
    out, _ = run(ssh, "lsusb")
    print("\n=== USB Devices ===")
    print(out)

    # 2. Find SDK
    print("\n=== Find SDK ===")
    out, _ = run(ssh, "find /home -name 'fingerprint.py' -path '*/SDK*' 2>/dev/null")
    print(out if out else "Not found in /home")
    out2, _ = run(ssh, "find /opt /usr/local -name 'fingerprint.py' 2>/dev/null")
    if out2:
        print(out2)
    # Also check home directory
    out3, _ = run(ssh, "ls -la ~/SDK*/fingerprint.py ~/fingerprint.py 2>/dev/null")
    if out3:
        print(out3)
    # Look broadly
    out4, _ = run(ssh, "locate fingerprint.py 2>/dev/null | head -10")
    if out4:
        print(f"locate: {out4}")

    # 3. Python version and pyusb
    print("\n=== Python ===")
    out, _ = run(ssh, "python3 --version")
    print(out)
    out, err = run(ssh, "python3 -c 'import usb.core; print(\"pyusb OK\")'")
    print(out if out else f"pyusb: NOT INSTALLED ({err[:100]})")
    out, _ = run(ssh, "pip3 list 2>/dev/null | grep -i usb")
    if out:
        print(f"pip: {out}")

    # 4. Check permissions on USB device
    print("\n=== USB Device Permissions ===")
    out, _ = run(ssh, "ls -la /dev/bus/usb/001/003 2>/dev/null")
    print(out if out else "device node not found")
    out, _ = run(ssh, "cat /etc/udev/rules.d/*fingerprint* 2>/dev/null || echo 'no udev rules'")
    print(out)

    ssh.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
