"""One bounded native retry with immutable CTC anchors and measured support."""
from dataclasses import replace
import wave
import numpy as np
from .timed import plan_timed_segments, expand_timed_segments_with_audio



def _decay_metrics(values, step):
    blocks = np.sqrt(np.mean(values[:len(values) // 2 * 2].reshape(-1, 2) ** 2, axis=1))
    if len(blocks) < 5:
        return None
    times = np.arange(len(blocks)) * 2 * step
    logs = np.log(np.maximum(blocks, 1e-12))
    slope, intercept = np.polyfit(times, logs, 1)
    total = float(np.sum((logs - np.mean(logs)) ** 2))
    fit = 1 - float(np.sum((logs - (slope * times + intercept)) ** 2)) / total if total > 0 else 0.
    ratio = float(blocks[-1] / blocks[0])
    rise = float(np.max(blocks[1:] / blocks[:-1]))
    return (fit, ratio, rise) if slope < 0 and fit >= .8 and ratio <= .1 and rise <= 1.5 else None


def _clipped_tail_context(item, diagnostic):
    """Expose a cropped connected vowel decay to MFA; never assign phones."""
    if not diagnostic or diagnostic.get("passed") or diagnostic.get("reason_code") != "alignment_acoustic_coverage":
        return item.segments, []
    if (diagnostic.get("bgm_suspects") or diagnostic.get("low_energy_phone_issues")
            or diagnostic.get("unowned_speech_regions")
            or any(issue.get("reason") in {"non_positive_or_nonfinite", "overlap_or_out_of_axis"}
                   for issue in diagnostic.get("structural_issues", []))):
        return item.segments, []
    vowels = {"a", "e", "i", "o", "u", "ɯ", "ɨ", "aː", "eː", "iː", "oː", "uː", "ɯː", "ɨː"}
    phones = diagnostic.get("raw_phones", [])
    with wave.open(str(item.working_audio), "rb") as source:
        rate = source.getframerate()
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise ValueError("clipped-tail context requires mono PCM16 working audio")
        audio = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float64) / 32768
    frame = max(1, round(rate * .01))
    rms = np.sqrt(np.mean(audio[:len(audio) // frame * frame].reshape(-1, frame) ** 2, axis=1))
    if len(rms) < 3:
        return item.segments, []
    step = frame / rate
    threshold = max(.001, 3 * float(np.percentile(rms, 15)))
    segments = list(item.segments)
    evidence = []
    for index, segment in enumerate(item.segments):
        owners = [p for p in phones if not p["silence"] and p["label"] in vowels
                  and abs(float(p["end"]) - segment.end) <= 1. / rate
                  and float(p["end"]) - float(p["start"]) >= .02
                  and p.get("token_index") == segment.last_token - 1]
        if not owners:
            continue
        first = round(segment.end / step)
        limit = int(np.floor(item.segments[index + 1].start / step + 1e-9)) if index + 1 < len(item.segments) else len(rms)
        cap = min(limit, first + round(.2 / step))
        stop = min(len(rms), limit, cap + 3)
        if first < 2 or first + 2 >= stop or not np.all(rms[first - 2:first + 2] > threshold):
            continue
        quiet = next((q for q in range(first + 2, stop - 2)
                      if q <= cap and np.all(rms[q:q + 3] <= threshold)), None)
        if quiet is None:
            continue
        anchor = round(segment.anchor_end / step) if segment.anchor_end is not None else first
        support_metrics = None
        if (0 <= anchor <= first and quiet - anchor <= round(.35 / step)
                and np.all(rms[anchor:quiet] > threshold)):
            support_metrics = _decay_metrics(rms[anchor:quiet], step)
        metrics = _decay_metrics(rms[first:quiet], step)
        if quiet - first <= round(.12 / step):
            if support_metrics is None or segment.acoustic_end_limit is None or segment.acoustic_end_limit >= quiet * step:
                continue
            metrics = support_metrics
        if metrics is None:
            continue
        fit, ratio, rise = metrics
        end = round((quiet + 3) * step, 6)
        support = round(quiet * step, 6)
        segments[index] = replace(segment, end=end, acoustic_end_limit=support)
        evidence.append({"segment": index, "before": segment.end, "after": end,
                         "acoustic_end_limit": support, "threshold": threshold,
                         "first_token": segment.first_token, "last_token": segment.last_token,
                         "anchor_end": segment.anchor_end,
                         "review_support_verified": support_metrics is not None,
                         "original_acoustic_end_limit": segment.acoustic_end_limit,
                         "decay_r_squared": fit, "decay_end_to_start_ratio": ratio,
                         "decay_max_adjacent_rise_ratio": rise,
                         "method": "native_retry_clipped_vowel_decay_context"})
    return tuple(segments), evidence


def prepare_context_retry(item, *, failed_postprocess=None):
    state = getattr(item, "state", None)
    if state is None or "review_segments" in state.values:
        return None
    values = state.values
    extended, evidence = _clipped_tail_context(item, failed_postprocess)
    merged = False
    if not evidence and len(item.segments) >= 2:
        planned = plan_timed_segments(
            values["source"].original, values["asr_result"].lexical_timestamps,
            values["tokens"], values["audio_info"].duration, min_segment_duration=2.4,
        )
        if len(planned) < len(item.segments):
            extended = expand_timed_segments_with_audio(planned, item.working_audio)
            merged = True
    if not merged and not evidence:
        return None
    review_segments = tuple(replace(old, acoustic_end_limit=proof["acoustic_end_limit"])
        if (proof := next((entry for entry in evidence
                          if entry["review_support_verified"] and entry["last_token"] == old.last_token
                          and entry["anchor_end"] == old.anchor_end), None)) else old
        for old in item.segments)
    retry_values = {**values, "segments": extended, "review_segments": review_segments}
    if review_segments != item.segments:
        retry_values["original_review_segments"] = item.segments
    if evidence:
        retry_values["clipped_tail_context"] = evidence
        retry_values["native_retry_segments"] = [index for index, segment in enumerate(extended)
            if not any((segment.start, segment.end, segment.first_token, segment.last_token)
                       == (old.start, old.end, old.first_token, old.last_token) for old in item.segments)]
    return replace(item, segments=extended, state=replace(state, values=retry_values))


def clipped_retry_inputs(batch, initial, changed_segments):
    """Reuse exact original native grids for unmodified clipped-retry crops."""
    import json
    import re
    import shutil
    from .hybrid_batch import _sha
    if not changed_segments:
        return batch, {}
    previous_by_alias = {(entry.utterance_id, entry.local_aliases): (entry, grid)
                         for entry, grid in initial.values()}
    reused, selected, evidence = {}, {}, []
    native_input = batch.root / "native-input"
    native_input.mkdir()
    reuse_root = batch.root / "reused-original"
    reuse_root.mkdir()
    for name, entry in batch.entries.items():
        if entry.utterance_id not in changed_segments or entry.segment_index in changed_segments[entry.utterance_id]:
            selected[name] = entry
            for suffix in (".wav", ".lab"):
                shutil.copy2(batch.corpus_dir / (name + suffix), native_input / (name + suffix))
            continue
        previous, grid = previous_by_alias[(entry.utterance_id, entry.local_aliases)]
        if (previous.local_aliases != entry.local_aliases or previous.wav_sha256 != entry.wav_sha256
                or _sha(batch.corpus_dir / (name + ".wav")) != entry.wav_sha256):
            raise ValueError("clipped retry original crop identity differs")
        mapping = dict(zip(previous.global_aliases, entry.global_aliases))
        pattern = re.compile(r'(?m)^(\s*text\s*=\s*)"([^"]+)"(\s*)$')
        raw = grid.read_text(encoding="utf-8")
        restored = pattern.sub(lambda m: m[1] + json.dumps(mapping[m[2]]) + m[3] if m[2] in mapping else m[0], raw)
        target = reuse_root / (name + ".TextGrid")
        target.write_text(restored, encoding="utf-8")
        reused[name] = target
        evidence.append({"entry": name, "source": entry.utterance_id,
                         "segment": entry.segment_index, "crop_sha256": entry.wav_sha256,
                         "original_textgrid": str(grid), "original_textgrid_sha256": _sha(grid),
                         "reused_textgrid_sha256": _sha(target)})
    (batch.root / "clipped-retry-selection.json").write_text(json.dumps({
        "native_entries": sorted(selected), "reused": evidence,
    }, ensure_ascii=False, indent=2) + "\n")
    return replace(batch, corpus_dir=native_input, entries=selected), reused
