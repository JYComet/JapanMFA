from __future__ import annotations

import array
import json
import math
import wave
from pathlib import Path

from japanmfa.asr.batch import ASRBatchRunner
from japanmfa.asr.qwen3 import ASRResult, Timestamp
from japanmfa.config import PipelineConfig
from japanmfa.errors import StageFailure


def _write_speech(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = array.array("h", (int(9000 * math.sin(2 * math.pi * 240 * i / 16000)) for i in range(4800)))
    with wave.open(str(path), "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        stream.writeframes(samples.tobytes())


class FakeASR:
    def __init__(self) -> None:
        self.calls: list[list[Path]] = []

    def transcribe(self, paths):
        self.calls.append(list(paths))
        return {
            path: ASRResult(
                path, "Japanese", "風。", "fake-asr", "fake-aligner", "風。",
                (Timestamp("風", 0.55, 0.75),),
                (Timestamp("。", 0.75, 0.75, "boundary_point"),),
            )
            for path in paths
        }


def test_asr_batch_exports_padded_audio_text_word_kana_and_timestamps(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write_speech(source / "speaker" / "a.wav")
    _write_speech(source / "speaker" / "b.wav")
    (source / "speaker" / "a.txt").write_text("これは入力側の参考文。", encoding="utf-8")
    output = tmp_path / "output"
    asr = FakeASR()

    result = ASRBatchRunner(PipelineConfig(), asr_client=asr).run(source, output)

    assert result.summary["counts"] == {"transcribed": 2, "skipped": 0, "failed": 0}
    assert len(asr.calls) == 1 and len(asr.calls[0]) == 2
    artifact = output / "speaker" / "a"
    assert (artifact / "a.txt").read_text(encoding="utf-8") == "風。\n"
    receipt = json.loads((artifact / "a.json").read_text(encoding="utf-8"))
    assert receipt["text"] == "風。"
    assert receipt["kana"] == "カゼ。"
    assert receipt["words"] == [{"text": "風", "kana": "カゼ", "start": 0.55, "end": 0.75}]
    assert receipt["punctuation"] == [{"text": "。", "start": 0.75, "end": 0.75, "source": "boundary_point"}]
    with wave.open(str(artifact / "a.wav")) as stream:
        assert stream.getframerate() == 16000
        assert stream.getnchannels() == 1
        assert stream.getnframes() >= 16000
        first = array.array("h", stream.readframes(4000))
        assert max(abs(sample) for sample in first) == 0
    assert (source / "speaker" / "a.txt").read_text(encoding="utf-8") == "これは入力側の参考文。"


def test_asr_batch_isolates_one_failed_item_after_batch_failure(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _write_speech(source / "a.wav")
    _write_speech(source / "b.wav")

    class OneBadASR(FakeASR):
        def transcribe(self, paths):
            if len(paths) > 1 or paths[0].name == "b.wav":
                raise StageFailure("asr", "worker_failed", "bad sample")
            return super().transcribe(paths)

    result = ASRBatchRunner(PipelineConfig(), asr_client=OneBadASR()).run(source, tmp_path / "out")

    assert result.summary["counts"] == {"transcribed": 1, "skipped": 0, "failed": 1}
    assert (tmp_path / "out" / "a" / "a.json").is_file()
    assert not (tmp_path / "out" / "b").exists()
    rows = [json.loads(line) for line in result.manifest_path.read_text(encoding="utf-8").splitlines()]
    assert [(row["utterance_id"], row["status"]) for row in rows] == [("a", "transcribed"), ("b", "failed")]
