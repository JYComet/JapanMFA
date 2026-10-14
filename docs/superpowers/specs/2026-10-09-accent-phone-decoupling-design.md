# Accent and phone alignment decoupling

## Intent

Continue ordinary phone alignment when tdmelodic returns malformed pitch markers but the underlying reading exactly matches the locked frontend reading. Preserve every previous successful output. Keep uncertain pitch visibly unknown instead of assigning a guessed H/L value. This is an isolated implementation; production publication awaits the user's review.

## Data flow

Accent parsing remains strict for valid output. For `malformed_output` alone, remove only `[` and `]` from the native result, normalize kana as the existing parser does, and require an exact match to the locked mora sequence. Return those morae with `tone=None`, retaining the raw native output and a recovery receipt. Reject empty output, mismatched readings, unsupported frontend text and native command failures as before.

G2P and MFA still use the locked kana reading and the current phone map. Project an all-unknown mora group to a `phone_tone` label of `??`; reject partially unknown groups. Keep the existing `phones`, `phone_kana`, words and timing checks. Extend TextGrid validation only to accept the explicit `??` label on a nonsilence phone. Record mixed predicted/unknown tone provenance when any `??` is present; leave prior successful artifacts byte identical.

## Verification

Test the malformed exact-reading fallback and its negative cases; test `??` projection and TextGrid validation; test single and bulk preparation paths. Replay the fixed 2,000-source input set with eight workers and compare all former successes byte for byte. Privately run full alignment and publication audit for recovered examples; missing TextGrids count as failures. Do not switch the active pipeline or publish corrected pairs in this step.
