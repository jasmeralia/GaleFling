Persist the current debugging state into `debug_state.md` at the project root.

## Steps

1. Synthesize the current issue state from the active conversation.
2. Write or overwrite `debug_state.md` with a structured, concise summary.
3. Return the full updated file contents.

## Required sections

```markdown
# GaleFling Debug State

## Issue Summary
...

## Reproduction Steps
1. ...

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

## Rules

- Maximum 5 active hypotheses. Remove or merge invalidated/redundant ones.
- Keep only evidence that affects current hypotheses or the next action.
- `Next Step` must be exactly one concrete action.
- Do not include full raw log content.
