#!/usr/bin/env python3
"""Small JSON protocol double for the Qwen3-ASR subprocess client tests."""

import json
import os
import sys
from pathlib import Path


def main() -> int:
    request = json.load(sys.stdin)
    record_path = os.environ.get("FAKE_QWEN_REQUEST_RECORD")
    if record_path:
        Path(record_path).write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")

    mode = os.environ.get("FAKE_QWEN_WORKER_MODE", "valid")
    if mode == "nonzero":
        print("worker failed", file=sys.stderr)
        return 7
    if mode == "malformed":
        sys.stdout.write("not-json\n")
        return 0

    paths = request["audio_paths"]
    if mode == "duplicate":
        result_paths = [paths[0], paths[0]]
    elif mode == "missing":
        result_paths = [paths[0]]
    else:
        result_paths = paths

    language = "English" if mode == "non_japanese" else "Japanese"
    results = [
        {"audio_path": path, "language": language, "text": "今日は晴れ" if i == 0 else "明日も晴れ"}
        for i, path in enumerate(result_paths)
    ]
    if request.get("aligner_model"):
        for row in results:
            row.update({
                "aligner_model": request["aligner_model"],
                "alignment_text": "今日は、晴れ。",
                "lexical_timestamps": [
                    {"text": "今日は", "start": 0.1, "end": 0.5},
                    {"text": "晴れ", "start": 0.7, "end": 1.0},
                ],
                "punctuation_timestamps": [
                    {"text": "、", "start": 0.5, "end": 0.7, "source": "lexical_gap"},
                    {"text": "。", "start": 1.0, "end": 1.0, "source": "boundary_point"},
                ],
            })
    print(json.dumps({"results": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
