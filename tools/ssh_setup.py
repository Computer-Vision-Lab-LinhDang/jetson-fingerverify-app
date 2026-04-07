#!/usr/bin/env python3
"""Setup Jetson Nano: explore existing project, install deps, init DB."""
import paramiko
import sys

HOST = "100.92.102.86"
USER = "binhan2"
PASS = "Anbinh@93"
PROJECT = "/home/binhan2/jetson-fingerverify-app"

def run(ssh, cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    code = stdout.channel.recv_exit_status()
    return out, err, code

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, username=USER, password=PASS, timeout=10)
    print(f"SSH connected to {USER}@{HOST}\n")

    # 1. Explore project directory
    print("=== Project Structure ===")
    out, _, _ = run(ssh, f"find {PROJECT} -maxdepth 3 -type f | head -60")
    print(out)

    # 2. Check for fingerprint.py SDK
    print("\n=== Find fingerprint SDK ===")
    out, _, _ = run(ssh, f"find /home/binhan2 -name 'fingerprint.py' 2>/dev/null | head -10")
    print(out if out else "Not found")

    # 3. Check existing Python packages
    print("\n=== Python packages ===")
    out, _, _ = run(ssh, "pip3 list 2>/dev/null | grep -iE 'usb|sqlite|numpy|pillow|click|yaml|fastapi|uvicorn'")
    print(out if out else "No matching packages")

    # 4. Check SQLite
    print("\n=== SQLite ===")
    out, _, _ = run(ssh, "sqlite3 --version 2>/dev/null")
    print(out if out else "sqlite3 not found")
    out, _, _ = run(ssh, "python3 -c 'import sqlite3; print(sqlite3.sqlite_version)'")
    print(f"Python sqlite3: {out}")

    # 5. Check disk space
    print("\n=== Disk Space ===")
    out, _, _ = run(ssh, "df -h /home")
    print(out)

    ssh.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
