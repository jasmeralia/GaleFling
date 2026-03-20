# Debug State Workflow

Purpose:
Support iterative GaleFling debugging with minimal context growth by separating log triage from persistent debug state.

## When to use this skill

Invoke this skill when the user uses any of these triggers:

- `triage_logs`
- `triage_crash`
- `save_debug`
- `resume_debug`
- `clean_debug`

If a user message consists primarily of one of those trigger phrases, treat that as an instruction to invoke the corresponding behavior.

## Core principles

- `debug_state.md` is the single persistent debugging memory across session resets.
- Do not rely on prior conversation state after a session reset.
- Minimize token usage by keeping state concise and evidence-focused.
- Prefer the newest relevant single log file only.
- Do not scan or summarize all logs unless explicitly asked.
- Do not include full raw logs in `debug_state.md`.

## Trigger behaviors

### triage_logs

Goal:
Analyze the newest relevant application log and form or refine hypotheses.

Steps:
1. Read `CLAUDE.md` for the configured log paths.
2. Identify the appropriate app log directory for the current environment.
3. List the directory and select the newest relevant app log.
4. Analyze only that single log file unless there is a strong reason to inspect a second file.
5. Return:
   - concise issue summary
   - relevant evidence
   - ranked hypotheses
   - recommended next step

Rules:
- Do not update `debug_state.md` unless explicitly asked.
- Extract only evidence relevant to the active issue.
- Trim log evidence aggressively.

### triage_crash

Goal:
Analyze the newest relevant crash log and form or refine hypotheses.

Steps:
1. Read `CLAUDE.md` for the configured log paths.
2. Identify the appropriate crash log location for the current environment.
3. Select the newest relevant crash log.
4. Analyze only that single log file unless there is a strong reason to inspect a second file.
5. Return:
   - concise crash summary
   - relevant evidence
   - ranked hypotheses
   - recommended next step

Rules:
- Do not update `debug_state.md` unless explicitly asked.
- Prefer crash logs over app logs for this trigger.
- Trim log evidence aggressively.

### save_debug

Goal:
Persist the current debugging state into `debug_state.md`.

Steps:
1. Update `debug_state.md` using the latest confirmed issue state.
2. Preserve only useful current information.
3. Return the full updated file.

Required sections:
- Issue Summary
- Reproduction Steps
- Observed Behavior
- Expected Behavior
- Current Hypotheses
- Evidence
- What Has Been Tried
- Files / Components of Interest
- Current Build Info
- Next Step

Rules:
- Maximum 5 active hypotheses.
- Remove invalidated hypotheses.
- Merge redundant or overlapping hypotheses.
- Keep only evidence that affects the current hypotheses or next action.
- Keep `Next Step` to exactly one concrete action.
- Do not include full raw logs.

### resume_debug

Goal:
Resume debugging from `debug_state.md` only.

Steps:
1. Read `debug_state.md`.
2. Treat it as the sole source of truth.
3. Continue investigation from the current saved state.
4. Focus on validating or eliminating the top hypothesis and on the saved `Next Step`.

Rules:
- Do not assume prior chat history.
- Do not re-expand scope unless the saved state or new evidence justifies it.

### clean_debug

Goal:
Reduce the size of `debug_state.md` while preserving useful reasoning state.

Steps:
1. Refactor `debug_state.md` for compactness and clarity.
2. Remove stale, redundant, or low-value material.
3. Return the full cleaned file.

Rules:
- Preserve current issue summary, top hypotheses, high-value evidence, and next step.
- Remove superseded evidence and dead-end hypotheses.
- Keep the file concise and high-signal.

## Output format for triage

Unless the user asks for a different format, use this structure:

### Issue
...

### Evidence
- ...
- ...

### Hypotheses
1. [High] ...
2. [Medium] ...
3. [Low] ...

### Recommended Next Step
...

## Recommended `debug_state.md` shape

```markdown
# GaleFling Debug State

## Issue Summary
...

## Reproduction Steps
1. ...
2. ...

## Observed Behavior
...

## Expected Behavior
...

## Current Hypotheses
1. [High] ...
2. [Medium] ...
3. [Low] ...

## Evidence
- ...
- ...

## What Has Been Tried
- Attempt:
  - Change made:
  - Result:

## Files / Components of Interest
- ...

## Current Build Info
- App version:
- Installer version:
- Platform:
- Log analyzed:
- Run timestamp:

## Next Step
...
```
