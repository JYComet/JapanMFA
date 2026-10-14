# Accent and Phone Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permit exact-reading phone alignment after malformed accent output while explicitly marking unverified tone.

**Architecture:** One strict fallback parser returns untoned morae only for malformed marker sequences with intact readings. Existing G2P/MFA stages continue, and projection/TextGrid publication represent unknown tone as `??` with conditional provenance.

**Tech Stack:** Python, pytest, pinned native tdmelodic/MFA Docker services.

**Spec:** `docs/superpowers/specs/2026-10-09-accent-phone-decoupling-design.md`

## Global Constraints

- Work only in the isolated branch until user approval.
- Preserve old successful artifacts byte for byte.
- Never infer an H/L tone from missing evidence.
- Keep the current phone mapping and acoustic/publication gates.

## Review Focus

- Reject an intact but different reading, empty output and non-marker corruption.
- Reject partially unknown mora groups; accept all-unknown groups as `??`.
- Keep valid accent outputs and metadata unchanged.
- Ensure both direct and bulk preparation use the same fallback.
- Count missing private TextGrids as failures in the audit.

## Task 1: Exact-reading fallback

- [x] Add failing unit tests for malformed exact-reading fallback and negative cases.
- [x] Run the tests and confirm the expected failures.
- [x] Implement the parser helper and pass the tests.
- [x] Integrate the helper into direct and bulk preparation with failing then passing tests.

## Task 2: Unknown tone projection and output

- [x] Add failing tests for `??` projection, mixed-tone rejection and TextGrid readback.
- [x] Run the tests and confirm the expected failures.
- [x] Implement projection, validation and conditional provenance; pass the tests.

## Task 3: Replay and review

- [x] Run the full test suite and pinned native tests.
- [x] Replay the fixed 2,000 inputs with eight workers and compare old successes byte for byte.
- [x] Run private MFA and pause/boundary/acoustic audit on recovered outputs.
- [x] Update `docs/alignment-issues.md` with evidence and remaining failures.
