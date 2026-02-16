import sys
import os
from pathlib import Path

# Add src to python path for all tests
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
