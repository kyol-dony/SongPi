"""Pytest config: make shazam.py importable from tests."""
import sys
from pathlib import Path

FILES_DIR = Path(__file__).resolve().parent.parent
if str(FILES_DIR) not in sys.path:
    sys.path.insert(0, str(FILES_DIR))
