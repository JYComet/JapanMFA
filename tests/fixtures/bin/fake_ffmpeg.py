#!/usr/bin/env python3
"""Minimal FFmpeg contract double: record argv and publish non-empty output."""

import json
import os
import sys
from pathlib import Path


def main() -> int:
    record_path = os.environ.get("FAKE_FFMPEG_ARGV_RECORD")
    if record_path:
        Path(record_path).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
    destination = Path(sys.argv[-1])
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
