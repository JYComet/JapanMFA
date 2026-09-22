#!/usr/bin/env python3
"""Deterministic fake for the narrow MFA G2P contract."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 5 or sys.argv[1] != "g2p" or sys.argv[3] != "japanese_mfa":
        return 2
    if record := os.environ.get("FAKE_MFA_ARGV"):
        Path(record).write_text(json.dumps(sys.argv), encoding="utf-8")
    input_path = Path(sys.argv[2])
    output_path = Path(sys.argv[4])
    readings = input_path.read_text(encoding="utf-8").splitlines()
    rows = {
        "キョウ": "k jo N",
        "ハレ": "h a r e",
    }
    mode = os.environ.get("FAKE_MFA_MODE", "")
    unique = list(dict.fromkeys(readings))
    output = [f"{reading}\t{rows[reading]}" for reading in unique if reading in rows]
    if mode == "missing" and output:
        output.pop()
    elif mode == "multiple" and output:
        output.append(output[0])
    elif mode == "oov":
        output.append("未知\tx i")
    elif mode == "mismatch" and output:
        output[0] = "別\tb e t u"
    output_path.write_text("\n".join(output) + ("\n" if output else ""), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
