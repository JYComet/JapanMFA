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
another pronunciation. MFA v3 supplies the final boundaries.

For each MFA phone:

- one contributing mora broadcasts its kana and tone;
- multiple phones from one mora repeat that mora's labels;
- a phone spanning multiple morae uses ordered labels, e.g. `オ|ー` and `H|L`;
- when a phone-map rule has the same number of morae and phones, ranges are
  paired one-to-one in order (for example, `オ,ー -> o,o` maps to `オ` then
  `ー`, preserving `H` then `L`);
- a rule with multiple morae and multiple phones of unequal cardinality must
  declare an explicit `mora_spans` list of half-open `[start, end]` ranges;
  the loader rejects such a rule when the ranges are absent or invalid;
- silence has empty `phone_kana` and `phone_tone` labels;
- no internal boundary is fabricated inside a single MFA interval.

The H/L long-phone rule is exact: when a long phone covers differently toned
morae, `phone_tone` contains the ordered composite joined by `|` (for example,
`H|L`), preserving mora order. A repeated same tone may remain a single label.
The original and kana tiers remain whole utterances; only the three lower tiers
share MFA boundaries.

Malformed brackets, reading mismatch, mora-count mismatch, unknown MFA phones,
or word/phone order mismatch fail closed with a reason code. They never trigger
a guessed accent or a made-up time split.
