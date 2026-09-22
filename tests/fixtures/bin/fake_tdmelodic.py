#!/usr/bin/env python3
"""Small line-oriented tdmelodic test double."""

from __future__ import annotations

import os
import sys


mode = os.environ.get("FAKE_TDMELODIC_MODE", "ok")
record_path = os.environ.get("FAKE_TDMELODIC_RECORD")
lines = sys.stdin.read().splitlines()
if record_path:
    with open(record_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
        if lines:
            handle.write("\n")

if mode == "nonzero":
    print("tdmelodic failed", file=sys.stderr)
    raise SystemExit(3)
if mode == "short":
    if lines:
        print("ガ[ッコウ]")
    raise SystemExit(0)
if mode == "blank":
    print("")
    print("ガ[ッコウ]")
    raise SystemExit(0)

for line in lines:
    surface, yomi = line.split(",", 1)
    if surface == "学校":
        print("ガ[ッコウ]")
    elif surface == "猫":
        print("ネ[コ")
    else:
        print(yomi)
