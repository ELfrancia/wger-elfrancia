# Implementation Plan: Persistent active-workout bubble actions

## Overview

Keep the global workout bubble and both navigation actions available whenever the server confirms an active workout session, regardless of whether a rest timer is running, paused, or expired.

## Architecture Decisions

- Treat the server-provided active session as the authority for whether the workout is active.
- Treat the rest-timer record as presentation state only; its expiry must not affect workout navigation.
- Keep the existing client-side URL cache only as a navigation convenience, never as proof that a workout is active.

## Task List

### Phase 1: Regression guard and fix

- [x] Task 1: Add regression tests, then make the global-bubble state and navigation independent from timer completion.

### Checkpoint: Complete

- [x] Targeted tests pass.
- [x] The Django template renders cleanly.
- [x] Graphify is refreshed after the source change.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Existing local UI edits overlap | Medium | Preserve them and limit the change to the bubble-state contract. |
| Browser-only state is hard to test | Medium | Add deterministic template-level regression assertions plus runtime checks. |
