"""Batch native preparation calls; keep the original per-source cache identities."""

from __future__ import annotations

import time
import os
import traceback
import tempfile
from pathlib import Path

from japanmfa.accent.parser import parse_accent_or_untoned
from japanmfa.accent.tdmelodic import AccentRequest
from japanmfa.cache import _MISSING, stage_fingerprint
from japanmfa.errors import StageFailure
from japanmfa.frontend.mora import segment_morae
from japanmfa.domain import Pronunciation, Token
from japanmfa.mfa.word_cache import WordCache
from japanmfa.mfa.g2p import MfaG2pClient, TerminalSokuonG2p
from japanmfa.output.reports import write_json


ACCENT_RECOVERY_SOURCE = Path(__file__).resolve().parents[1] / "accent/model_recovery.py"


def prime_preparation_cache(frontends, cache, accent, g2p, model, evidence):
    from japanmfa.pipeline import _adapter_id, _mora_payload, _token_payload
    evidence.mkdir(parents=True, exist_ok=True)
    events = []
    failures = {}
    words = WordCache(os.environ.get("JAPANMFA_WORD_CACHE_DIR", cache.root))
    model_root = Path(os.environ.get("MFA_ROOT_DIR", "/nonexistent"))
    model_archive = model_root / "pretrained_models/g2p" / (model + ".zip")
    accent_identity = stage_fingerprint("native-accent-word-v1", {
        "adapter": _adapter_id(accent), "model": os.environ.get("JAPANMFA_ACCENT_MODEL_ID", "adapter-defined"),
        "implementation": Path(__file__), "resident": Path(__file__).with_name("native_resident.py"),
        "recovery": ACCENT_RECOVERY_SOURCE})
    g2p_identity = stage_fingerprint("native-g2p-word-v1", {
        "adapter": _adapter_id(g2p), "model": model, "archive": model_archive,
        "implementation": Path(__file__).with_name("g2p.py"), "resident": Path(__file__).with_name("native_resident.py")})
    entries = []
    for item in frontends:
        accent_fp = stage_fingerprint("accent", {"frontend": item.payload, "adapter": _adapter_id(accent)})
        g2p_fp = stage_fingerprint("g2p", {"tokens": _token_payload(item.tokens), "model": model, "adapter": _adapter_id(g2p)})
        entries.append((item, accent_fp, g2p_fp))

    def cached(stage, fp):
        return cache._load_complete(cache.directory(stage, fp), fp) is not _MISSING

    def dispatch(group, stage, invoke, publish):
        if not group:
            return
        call_dir = Path(tempfile.mkdtemp(prefix=f"{stage}-", dir=evidence))
        event = {"stage": stage, "sources": [x[0].utterance_id for x in group]}
        events.append(event)
        started = time.monotonic()
        try:
            output = invoke(group, call_dir)
        except StageFailure as exc:
            event.update(status="split_or_serial_fallback", reason=exc.reason_code)
            write_json(call_dir / "failure.json", {"reason": exc.reason_code, "message": str(exc)})
            if len(group) > 1:
                mid = len(group) // 2
                dispatch(group[:mid], stage, invoke, publish)
                dispatch(group[mid:], stage, invoke, publish)
        else:
            event["status"] = "complete"
            publish(group, output, call_dir)
        finally:
            event["seconds"] = time.monotonic() - started
            write_json(evidence / "batch-preparation.json", {"sources": len(frontends), "calls": events})

    def accent_invoke(group, call_dir):
        pairs = tuple(dict.fromkeys((token.surface, token.reading)
                      for item, *_ in group for token in item.tokens))
        marked = {}
        misses = []
        for pair in pairs:
            value = words.get(accent_identity, "accent", pair)
            if value is None:
                misses.append(pair)
            else:
                marked[pair] = value
        requests = tuple(AccentRequest(i, surface, reading) for i, (surface, reading) in enumerate(misses))
        write_json(call_dir / "requests.json", {"requests": [vars(r) for r in requests], "requested_pairs": pairs})
        rejected = {}
        repairs = {}
        if requests:
            if hasattr(accent, "predict_partial_detailed"):
                outputs, rejected, repairs = accent.predict_partial_detailed(requests)
            elif hasattr(accent, "predict_partial"):
                outputs, rejected = accent.predict_partial(requests)
            else:
                outputs = accent.predict(requests)
            if set(outputs) & set(rejected) or set(outputs) | set(rejected) != {r.token_index for r in requests}:
                raise StageFailure("accent", "output_coverage_mismatch", "batch accent coverage differs")
            if set(repairs) - set(outputs):
                raise StageFailure("accent", "output_coverage_mismatch", "batch accent repair coverage differs")
            for request in requests:
                if request.token_index in rejected:
                    continue
                output = outputs[request.token_index]
                marked[request.surface, request.yomi] = output
                try:
                    token = Token(0, 0, len(request.surface), request.surface, (), request.yomi, "sudachi")
                    parse_accent_or_untoned(output, segment_morae(token))
                except (StageFailure, ValueError):
                    continue
                words.put(accent_identity, "accent", (request.surface, request.yomi), output)
        words.commit()
        rejected_pairs = {(r.surface, r.yomi): rejected[r.token_index] for r in requests if r.token_index in rejected}
        for item, *_ in group:
            for token in item.tokens:
                if (token.surface, token.reading) in rejected_pairs:
                    reason = rejected_pairs[token.surface, token.reading]
                    failures[item.utterance_id] = StageFailure("accent", reason, "native accent request failed", {"token_index": token.index})
                    break
        write_json(call_dir / "outputs.json", {"outputs": outputs if requests else {},
                                               "failures": rejected, "repairs": repairs})
        return marked

    def accent_publish(group, marked, call_dir):
        for item, fp, _ in group:
            if item.utterance_id in failures:
                continue
            selected = {t.index: marked[t.surface, t.reading] for t in item.tokens}
            try:
                morae = {t.index: parse_accent_or_untoned(selected[t.index], segment_morae(t)) for t in item.tokens}
            except StageFailure as exc:
                failures[item.utterance_id] = exc
                continue
            except ValueError as exc:
                failures[item.utterance_id] = StageFailure("accent", "unexpected_exception", str(exc),
                                                          {"traceback": traceback.format_exc()})
                continue
            unknown = {str(index): "malformed_output_exact_reading" for index, values in morae.items()
                       if any(value.tone is None for value in values)}
            payload = {"morae": _mora_payload(morae), "tdmelodic": selected,
                       **({"unknown_tone_indices": unknown} if unknown else {})}
            cache.load_or_run("accent", fp, lambda _path, p=payload: p)

    dispatch([x for x in entries if not cached("accent", x[1])], "accent", accent_invoke, accent_publish)

    def g2p_invoke(group, call_dir):
        readings = tuple(dict.fromkeys(t.reading for item, *_ in group for t in item.tokens))
        write_json(call_dir / "requests.json", {"requests": readings})
        found = {}
        misses = []
        for reading in readings:
            value = words.get(g2p_identity, "g2p", reading)
            if value is None:
                misses.append(reading)
            else:
                found[reading] = Pronunciation(reading, tuple(value["phones"]), tuple(tuple(v) for v in value["alternates"]))
        if misses:
            pronunciations = (g2p.pronounce(tuple(misses), call_dir, num_jobs=16)
                              if isinstance(g2p, (MfaG2pClient, TerminalSokuonG2p))
                              else g2p.pronounce(tuple(misses), call_dir))
            if len(pronunciations) != len(misses) or any(p.reading != r or not p.phones for p, r in zip(pronunciations, misses)):
                raise StageFailure("mfa_g2p", "output_coverage_mismatch", "batch G2P order/coverage differs")
            for pronunciation in pronunciations:
                found[pronunciation.reading] = pronunciation
                words.put(g2p_identity, "g2p", pronunciation.reading, {"phones": pronunciation.phones, "alternates": pronunciation.alternates})
        words.commit()
        write_json(call_dir / "outputs.json", {"outputs": [vars(found[r]) for r in readings], "native_misses": misses})
        return found

    def g2p_publish(group, pronunciations, call_dir):
        raw = (call_dir / "g2p_output.dict").read_text(encoding="utf-8") if (call_dir / "g2p_output.dict").is_file() else ""
        for item, _, fp in group:
            selected = tuple(pronunciations[t.reading] for t in item.tokens)
            payload = {"pronunciations": [{"reading": p.reading, "phones": list(p.phones),
                         "alternates": [list(v) for v in p.alternates]} for p in selected]}
            readings = tuple(t.reading for t in item.tokens)
            def produce(path, payload=payload, readings=readings):
                (path / "g2p_input.txt").write_text("".join(r + "\n" for r in readings), encoding="utf-8")
                lines = [p.reading + " " + " ".join(variant)
                         for p in selected for variant in (p.phones, *p.alternates)]
                (path / "g2p_output.dict").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
                write_json(path / "batch-provenance.json", {"native_call": str(call_dir), "full_request": list(readings)})
                return payload
            cache.load_or_run("g2p", fp, produce)

    dispatch([x for x in entries if cached("accent", x[1]) and not cached("g2p", x[2])],
             "g2p", g2p_invoke, g2p_publish)

    write_json(evidence / "batch-preparation.json", {"sources": len(frontends), "calls": events})
    write_json(evidence / "word-cache.json", {"hits": words.hits, "misses": words.misses,
                                            "accent_identity": accent_identity, "g2p_identity": g2p_identity})
    words.close()
    return failures
