"""Expose the synthetic extraction checks to standard unittest discovery."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fluid_ici.preprocessing.test_protocol import ProtocolTests

