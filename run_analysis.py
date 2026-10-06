#!/usr/bin/env python3
"""Fit both samples and compute incremental-intervention curves and regions."""
import os
from pathlib import Path
import sys

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "2")
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fluid_ici.analysis.runner import main

if __name__ == "__main__":
    main()
