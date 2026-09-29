from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.galgame_qwen_ctc import atomic_publish_textgrid, catalog, lexical_words, render_textgrid, reshard


def test_catalog_pairs_matching_wav_txt_and_shards_without_changing_source(tmp_path: Path) -> None:
    source = tmp_path / 'input'
    for game in ('a', 'b'):
        (source / game / 'wav').mkdir(parents=True)
        (source / game / 'txt').mkdir()
    (source / 'a/wav/one.wav').write_bytes(b'RIFF')
    (source / 'a/wav/only_audio.wav').write_bytes(b'RIFF')
    (source / 'a/txt/one.txt').write_text('世界', encoding='utf-8')
    (source / 'a/txt/only_text.txt').write_text('欠落', encoding='utf-8')
    (source / 'b/wav/two.wav').write_bytes(b'RIFF')
    (source / 'b/txt/two.txt').write_text('大丈夫', encoding='utf-8')

    state = tmp_path / 'state'
    summary = catalog(source, state, shards=2)

    assert summary['paired'] == 2
    assert summary['missing_txt'] == 1
    assert summary['missing_wav'] == 1
    rows = [json.loads(line) for path in sorted(state.glob('shard_*.jsonl')) for line in path.read_text().splitlines()]
    assert {row['stem'] for row in rows} == {'one', 'two'}
    assert all(Path(row['ctc']).parent.name == 'ctc' for row in rows)
    assert not list(source.rglob('ctc'))


def test_catalog_preserves_uppercase_source_extensions(tmp_path: Path) -> None:
    root = tmp_path / 'input' / 'game'
    (root / 'wav').mkdir(parents=True)
    (root / 'txt').mkdir()
    (root / 'wav/voice.WAV').write_bytes(b'RIFF')
    (root / 'txt/voice.TXT').write_text('声', encoding='utf-8')

    state = tmp_path / 'state'
    summary = catalog(tmp_path / 'input', state, shards=1)
    row = json.loads((state / 'shard_0.jsonl').read_text().strip())

    assert summary['paired'] == 1
    assert row['wav'].endswith('voice.WAV')
    assert row['txt'].endswith('voice.TXT')
    assert row['ctc'].endswith('voice.TextGrid')


def test_catalog_keeps_dots_inside_audio_stems(tmp_path: Path) -> None:
    root = tmp_path / 'input' / 'game'
    (root / 'wav').mkdir(parents=True)
    (root / 'txt').mkdir()
    (root / 'wav/voice.alt.wav').write_bytes(b'RIFF')
    (root / 'txt/voice.alt.txt').write_text('声', encoding='utf-8')

    state = tmp_path / 'state'
    catalog(tmp_path / 'input', state, shards=1)
    row = json.loads((state / 'shard_0.jsonl').read_text().strip())

    assert row['ctc'].endswith('voice.alt.TextGrid')


def test_reshard_preserves_every_pair_and_missing_counts(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    source.mkdir()
    rows = [{'stem': f'voice_{index}'} for index in range(5)]
    (source / 'shard_0.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows[:3]))
    (source / 'shard_1.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows[3:]))
    (source / 'catalog_summary.json').write_text(json.dumps({
        'categories': 1, 'wav': 6, 'txt': 5, 'paired': 5,
        'missing_txt': 1, 'missing_wav': 0, 'shard_counts': [3, 2],
    }))
    (source / 'catalog_errors.jsonl').write_text('{"reason":"missing_txt"}\n')

    target = tmp_path / 'target'
    summary = reshard(source, target, shards=4)

    assert summary['shard_counts'] == [2, 1, 1, 1]
    assert summary['paired'] == 5
    assert summary['missing_txt'] == 1
    assert (target / 'catalog_errors.jsonl').read_text() == '{"reason":"missing_txt"}\n'
    actual = [json.loads(line) for path in sorted(target.glob('shard_*.jsonl')) for line in path.read_text().splitlines()]
    assert sorted(actual, key=lambda row: row['stem']) == rows


def test_reshard_repairs_dotted_output_names_from_older_catalog(tmp_path: Path) -> None:
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'shard_0.jsonl').write_text(json.dumps({
        'stem': 'voice.alt', 'ctc': '/game/ctc/voice.TextGrid',
    }) + '\n')
    (source / 'catalog_summary.json').write_text(json.dumps({
        'paired': 1, 'missing_txt': 0, 'missing_wav': 0, 'shard_counts': [1],
    }))

    target = tmp_path / 'target'
    summary = reshard(source, target, shards=2)
    row = json.loads((target / 'shard_0.jsonl').read_text())

    assert summary['repaired_ctc_paths'] == 1
    assert row['ctc'] == '/game/ctc/voice.alt.TextGrid'


def test_render_textgrid_preserves_word_gaps_and_zero_duration_points(tmp_path: Path) -> None:
    from praatio import textgrid

    output = tmp_path / 'sample.TextGrid'
    output.write_text(render_textgrid(3.0, [
        {'text': '世界', 'start': 0.5, 'end': 1.2},
        {'text': 'が', 'start': 1.2, 'end': 1.2},
        {'text': '大丈夫', 'start': 2.0, 'end': 2.8},
    ]), encoding='utf-8')
    parsed = textgrid.openTextgrid(str(output), includeEmptyIntervals=True)

    assert [(entry.start, entry.end, entry.label) for entry in parsed.getTier('words').entries] == [
        (0.0, 0.5, ''), (0.5, 1.2, '世界'), (1.2, 2.0, ''),
        (2.0, 2.8, '大丈夫'), (2.8, 3.0, ''),
    ]
    assert [(entry.time, entry.label) for entry in parsed.getTier('zero_duration').entries] == [(1.2, 'が')]


def test_render_textgrid_rejects_out_of_bounds_or_overlapping_words() -> None:
    with pytest.raises(ValueError, match=r"exceeds audio duration.*end=1\.200000.*duration=1\.000000"):
        render_textgrid(1.0, [{'text': '世界', 'start': 0.2, 'end': 1.2}])
    with pytest.raises(ValueError, match='overlap'):
        render_textgrid(2.0, [
            {'text': '世', 'start': 0.2, 'end': 1.0},
            {'text': '界', 'start': 0.9, 'end': 1.2},
        ])


def test_render_textgrid_uses_a_single_rounded_audio_bound(tmp_path: Path) -> None:
    from praatio import textgrid

    output = tmp_path / 'boundary.TextGrid'
    value = render_textgrid(1.0000004, [
        {'text': '声', 'start': 0.5, 'end': 1.0000009},
    ])
    output.write_text(value, encoding='utf-8')

    parsed = textgrid.openTextgrid(str(output), includeEmptyIntervals=True)
    assert value.splitlines()[4] == 'xmax = 1.000001'
    assert parsed.maxTimestamp >= max(entry.end for entry in parsed.getTier('words').entries)


def test_atomic_publish_does_not_unlink_after_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / 'ctc' / 'voice.TextGrid'
    output.parent.mkdir()
    original_unlink = Path.unlink

    def reject_cleanup(self: Path, *args, **kwargs):
        raise AssertionError(f'unexpected SMB unlink after successful publish: {self}')

    monkeypatch.setattr(Path, 'unlink', reject_cleanup)
    atomic_publish_textgrid(output, 'textgrid')
    assert output.read_text() == 'textgrid'
    monkeypatch.setattr(Path, 'unlink', original_unlink)


def test_lexical_words_accepts_qwen_punctuation_only_item() -> None:
    from types import SimpleNamespace
    result = SimpleNamespace(items=[
        SimpleNamespace(text='さ', start_time=0.48, end_time=0.72),
        SimpleNamespace(text='Let', start_time=1.20, end_time=1.44),
        SimpleNamespace(text="'", start_time=1.44, end_time=1.44),
        SimpleNamespace(text='s', start_time=1.68, end_time=1.84),
        SimpleNamespace(text='go', start_time=1.84, end_time=2.56),
    ])

    words = lexical_words("さ、Let's go!", result)

    assert [item['text'] for item in words] == ['さ', 'Let', 's', 'go']
    assert words[2]['start'] == 1.68
