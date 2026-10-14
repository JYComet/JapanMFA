# Accent and phone mapping

For every pronounced Sudachi token, JapanMFA calls exactly
`tdmelodic sy2a(surface, yomi)`, where `yomi` is the already locked reading.
tdmelodic may add bracket events but cannot replace the reading. The parser
normalizes hiragana/katakana, verifies that the unmarked output equals the
locked reading, and assigns exactly one `H` or `L` to each mora.
At a mora boundary, `[` raises the following mora and `]` lowers the following
mora. A final `]` is also accepted as the fall after the final mora (without
changing that mora's assigned label); a final `[` remains malformed because it
cannot affect a following mora.

The mora sequence is then paired with the single MFA-G2P phone sequence selected
for that token occurrence. MFA alignment is run against safe per-occurrence
ASCII aliases and a locked dictionary, so repeated surface forms cannot select
another pronunciation. MFA v3 supplies the phonetic boundaries; a separately
audited acoustic postprocessor may refine only the outer speech edges.

For each MFA phone:

- one contributing mora broadcasts its kana and a constant contour (`H → HH`, `L → LL`);
- multiple phones from one mora repeat that mora's labels;
- a phone spanning multiple morae uses ordered kana labels, e.g. `オ|ー`,
  and the contour `HL` for an H mora followed by an L mora;
- when a phone-map rule has the same number of morae and phones, ranges are
  paired one-to-one in order (for example, `オ,ー -> o,o` maps to `オ` then
  `ー`, preserving `H` then `L`);
- a rule with multiple morae and multiple phones of unequal cardinality must
  declare an explicit `mora_spans` list of half-open `[start, end]` ranges;
  the loader rejects such a rule when the ranges are absent or invalid;
- silence carries no mora or tone in the internal annotation; at publication,
  its pause or punctuation label is repeated on `phones`, `phone_kana`, and
  `phone_tone` so the three timed tiers keep the same complete partition;
- no internal boundary is fabricated inside a single MFA interval.

`phone_tone` uses `HH`, `LL`, `HL`, or `LH` on speech phones with known mora tones.
It uses `??` only when every contributing mora tone is unknown because the
lexical-accent prediction was unusable while the locked reading still matched.
A phone combining known and unknown mora tones fails rather than receiving a
guessed contour. The four known labels are pitch-state contours, not a statement
that every phone has two morae. For
longer spans, HHH becomes HH, HHL becomes HL, and LHH becomes LH. More than one
change (HLH or LHL) cannot be represented faithfully by these four labels and
fails with `unsupported_tone_contour`. Complete ordered mora labels remain in
`alignment.json` and `postprocess.json`; no neighboring phone's tone is borrowed.
The original and kana tiers remain whole utterances; only the three lower tiers
share the same complete time partition, including explicit blank intervals.

These labels project tdmelodic's predicted lexical accent. They are not
measured audio F0: consonants can inherit mora accent even when unvoiced, and
expressive speech or laughter can differ from the predicted lexical pattern.
Pitch changes generally preserve the segmental phone identity, but can change
the accent and distinguish words in Japanese. Vowel length is a separate
phonological distinction from pitch.

Malformed brackets, reading mismatch, mora-count mismatch, unknown MFA phones,
or word/phone order mismatch fail closed with a reason code. They never trigger
a guessed accent or a made-up time split.
