# Reading overrides

SudachiPy supplies the default reading. A YAML override addresses one concrete
occurrence by utterance ID, source character span, and expected surface:

```yaml
utterances:
  speaker_a/001:
    readings:
      - span: [4, 6]
        surface: 今日
        kana: キョウ
```

`span` uses the normalized processing text's half-open character coordinates.
The surface must match that exact span and `kana` must normalize to a supported
non-empty katakana reading. The override applies to that occurrence only;
repeated compounds require repeated span entries. A bad span, surface, or
reading is a typed failure and is never guessed or moved to another token.

Overrides lock pronunciation before mora segmentation, tdmelodic, and MFA G2P.
They therefore affect all downstream audit files but do not alter the original
TextGrid tier. The `kana` tier displays the complete resulting locked reading,
while `phone_kana` is only a visualization aid projected onto MFA intervals.

In v1, compound-word and homograph selection is intentionally explicit. Add an
override for each ambiguous occurrence and record unresolved cases in
`docs/limitations.md` rather than relying on sentence-level inference.
