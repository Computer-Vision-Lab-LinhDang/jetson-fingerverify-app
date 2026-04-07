#!/usr/bin/env python3
"""Launch MDGT Edge PyQt5 Desktop Application."""
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mdgt_edge.ui.main_window import main

if __name__ == "__main__":
    main()
