# Alignment issue tracking

For alignment, phone boundaries, silence, punctuation, energy checks, or output
publication problems, use `docs/alignment-issues.md` as the single ongoing issue
ledger. Append every newly found issue or recurrence there with sample paths,
time coordinates, evidence, root cause, fix, verification, and remaining scope.
Update an existing issue for the same root cause; retain historical evidence
and distinguish automatic checks from manual phonetic ground truth.

Before publishing corrected TextGrid/WAV pairs, retain the prior artifacts and
hashes, run relevant regression tests, and use `tools/audit_textgrid_pauses.py`
to check adjacent pauses, shared punctuation boundaries, and acoustic coverage.
Record failed samples as failures rather than treating missing TextGrids as
successful validation.
