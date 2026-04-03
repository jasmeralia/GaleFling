Analyze the newest relevant GaleFling application log and form or refine hypotheses about the active issue.

## Steps

1. Read `CLAUDE.md` for the configured log paths (WSL: `/mnt/c/Users/storm/AppData/Roaming/GaleFling/logs/`).
2. List the log directory and select the newest relevant application log file.
3. Read only that single file. Do not scan additional logs unless there is a strong reason.
4. Analyze the log content in the context of any active debugging session.
5. Return:
   - Concise issue summary
   - Relevant evidence (trimmed aggressively — extract only what affects the active issue)
   - Ranked hypotheses (max 5), each labeled [High], [Medium], or [Low]
   - Recommended next step (one concrete action)

## Output format

### Issue
...

### Evidence
- ...

### Hypotheses
1. [High] ...
2. [Medium] ...

### Recommended Next Step
...

## Rules

- Do not update `debug_state.md` unless explicitly asked.
- Do not include full raw log content in the response.
- Prefer the single newest relevant log file.
