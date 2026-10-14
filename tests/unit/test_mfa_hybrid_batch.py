from __future__ import annotations

import wave
from pathlib import Path

from japanmfa.mfa.hybrid_batch import BatchGridRunner, build_batch_corpus, build_dual_batch_corpus
from japanmfa.mfa.timed import TimedSegment
from japanmfa.pipeline import MfaPrepared


def _prepared(root: Path, name: str, phones: str) -> MfaPrepared:
    artifact = root / name
    corpus = artifact / "mfa" / "corpus"
    corpus.mkdir(parents=True)
    wav = corpus / f"{name}.wav"
    with wave.open(str(wav), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        out.writeframes(b"\0\0" * 16000)
    (corpus / f"{name}.lab").write_text("jmfa_000000\n")
    dictionary = artifact / "mfa" / "dictionary.dict"
    dictionary.write_text(f"jmfa_000000 {phones}\n")
    return MfaPrepared(name, artifact, wav, dictionary, wav, ("jmfa_000000",),
                       (TimedSegment(.2, .8, 0, 1, .2, .8),))


def test_batch_corpus_keeps_occurrence_pronunciations_separate(tmp_path: Path) -> None:
    first = _prepared(tmp_path, "first", "a")
    second = _prepared(tmp_path, "second", "i")
    batch = build_batch_corpus((first, second), tmp_path / "batch", "whole")

    assert len(batch.entries) == 2
    assert (batch.corpus_dir / "b0000.lab").read_text().strip() == "jmfa_000000"
    assert (batch.corpus_dir / "b0001.lab").read_text().strip() == "jmfa_000001"
    assert batch.dictionary.read_text().splitlines() == ["jmfa_000000 a", "jmfa_000001 i"]


def test_timed_batch_uses_exact_segment_sample_bounds(tmp_path: Path) -> None:
    item = _prepared(tmp_path, "first", "a")
    batch = build_batch_corpus((item,), tmp_path / "batch", "timed")
    with wave.open(str(batch.corpus_dir / "b0000_000.wav"), "rb") as audio:
        assert audio.getnframes() == 9600
    assert batch.entries["b0000_000"].segment_index == 0


def test_anchored_batch_keeps_full_wav_and_writes_ctc_windows(tmp_path: Path) -> None:
    item = _prepared(tmp_path, "first", "a")
    batch = build_batch_corpus((item,), tmp_path / "batch", "anchored")

    with wave.open(str(batch.corpus_dir / "b0000.wav"), "rb") as audio:
        assert audio.getnframes() == 16000
    anchor = (batch.corpus_dir / "b0000.TextGrid").read_text()
    assert 'name = "speaker"' in anchor
    assert 'xmin = 0.2' in anchor
    assert 'xmax = 0.8' in anchor
    assert 'text = "jmfa_000000"' in anchor
    assert not (batch.corpus_dir / "b0000_000.wav").exists()


def test_dual_batch_loads_both_candidates_with_one_dictionary(tmp_path: Path) -> None:
    first = _prepared(tmp_path, "first", "a")
    second = _prepared(tmp_path, "second", "i")
    combined, whole, anchored = build_dual_batch_corpus(
        (first, second), tmp_path / "dual",
    )

    assert set(combined.entries) == {"wb0000", "wb0001", "ab0000", "ab0001"}
    assert set(whole.entries) == {"wb0000", "wb0001"}
    assert set(anchored.entries) == {"ab0000", "ab0001"}
    assert combined.dictionary == whole.dictionary == anchored.dictionary
    assert combined.dictionary.read_text().splitlines() == [
        "jmfa_000000 a", "jmfa_000001 i",
    ]
    assert (combined.corpus_dir / "wb0000.lab").read_text().strip() == "jmfa_000000"
    assert 'name = "speaker"' in (combined.corpus_dir / "ab0000.TextGrid").read_text()
    with wave.open(str(combined.corpus_dir / "ab0001.wav"), "rb") as audio:
        assert audio.getnframes() == 16000


def test_batch_runner_restores_local_alias_and_checks_audio(tmp_path: Path) -> None:
    first = _prepared(tmp_path, "first", "a")
    batch = build_batch_corpus((first,), tmp_path / "batch", "whole")
    raw = tmp_path / "b0000.TextGrid"
    raw.write_text('''File type = "ooTextFile"
Object class = "TextGrid"
xmin = 0
xmax = 1
tiers? <exists>
size = 2
item []:
    item [1]:
        class = "IntervalTier"
        name = "words"
        xmin = 0
        xmax = 1
        intervals: size = 1
        intervals [1]:
            xmin = 0
            xmax = 1
            text = "jmfa_000000"
    item [2]:
        class = "IntervalTier"
        name = "phones"
        xmin = 0
        xmax = 1
        intervals: size = 1
        intervals [1]:
            xmin = 0
            xmax = 1
            text = "a"
''')
    runner = BatchGridRunner(batch, {"b0000": raw}, tmp_path / "hydrated")

    result = runner.align(first.corpus_audio.parent, first.dictionary,
                          tmp_path / "unused", tmp_path / "unused-work")
    assert result.is_file()
    assert 'text = "jmfa_000000"' in result.read_text()


def test_partial_batch_missing_grid_is_a_typed_item_failure(tmp_path: Path) -> None:
    import pytest
    from japanmfa.errors import StageFailure

    first = _prepared(tmp_path, 'first', 'a')
    batch = build_batch_corpus((first,), tmp_path / 'batch', 'whole')
    runner = BatchGridRunner(batch, {}, tmp_path / 'hydrated', allow_partial=True)
    with pytest.raises(StageFailure) as failure:
        runner.align(first.corpus_audio.parent, first.dictionary,
                     tmp_path / 'unused', tmp_path / 'unused-work')
    assert failure.value.reason_code == 'missing_output'
    assert not (tmp_path / 'hydrated').exists()


def test_partial_grid_provider_still_rejects_foreign_output(tmp_path: Path) -> None:
    import pytest
    from japanmfa.errors import StageFailure

    first = _prepared(tmp_path, 'first', 'a')
    batch = build_batch_corpus((first,), tmp_path / 'batch', 'whole')
    with pytest.raises(StageFailure) as failure:
        BatchGridRunner(batch, {'foreign': tmp_path / 'foreign.TextGrid'},
                        tmp_path / 'hydrated', allow_partial=True)
    assert failure.value.reason_code == 'output_coverage_mismatch'
