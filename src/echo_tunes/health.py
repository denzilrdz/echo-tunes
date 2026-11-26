"""Process health numbers, shown on /healthz and used by the memory soak test."""

from __future__ import annotations

import resource
import sys
from pathlib import Path


def memory_mb() -> float:
    """Current resident memory of this process in MB (peak on systems without /proc)."""
    statm = Path("/proc/self/statm")
    if statm.exists():
        pages = int(statm.read_text().split()[1])
        return round(pages * resource.getpagesize() / 1_048_576, 1)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1_048_576 if sys.platform == "darwin" else 1024), 1)
