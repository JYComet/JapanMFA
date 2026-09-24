from pathlib import Path
import re


def test_upstream_regression_ledger_has_exact_pinned_id_set() -> None:
    path = Path(__file__).parents[2] / "docs" / "upstream-regression-applicability-20260923.md"
    rows = []
    allowed = {
        "ported_verified", "covered_existing", "diagnostic_only",
        "blocked_missing_evidence", "not_applicable_language",
        "not_applicable_architecture", "rejected_withdrawn",
    }
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\| (\d+) \| .* \| `c2bcdf6` \| `([^`]+)` \| (.*) \|$", line)
        if match:
            rows.append((int(match.group(1)), match.group(2), match.group(3)))
    ids = [row[0] for row in rows]
    assert len(rows) == 257
    assert len(set(ids)) == len(ids)
    assert set(ids) == set(range(1, 259)) - {242}
    assert all(disposition in allowed for _id, disposition, _evidence in rows)
    for _id, disposition, evidence in rows:
        if disposition in {"ported_verified", "covered_existing"}:
            assert "tests/" in evidence or "postprocess." in evidence
        elif disposition == "diagnostic_only":
            assert any(field in evidence for field in (
                "postprocess", "diagnostic", "structural_issues", "tier_discontinuities",
                "short_phone_issues", "marker", "source text", "tests/", "audio.json",
                "MFA", "output", "punctuation", "native-rate", "blocked_upstream_capabilities",
            ))
        elif disposition == "blocked_missing_evidence":
            assert "impact" in evidence or "unavailable" in evidence or "block" in evidence
