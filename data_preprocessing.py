#!/usr/bin/env python3
"""Reproduce the two analysis samples from an authorized raw MIMIC-IV 3.1 copy."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fluid_ici.preprocessing.pipeline import main

if __name__ == "__main__":
    main()
