Resume the active debugging session from `debug_state.md`.

## Steps

1. Read `debug_state.md` from the project root.
2. Treat it as the sole source of truth. Do not assume prior chat history exists.
3. Summarize:
   - Current issue
   - Active hypotheses (with confidence levels)
   - What has been tried
   - The saved next step
4. Ask whether to proceed with the saved next step or if new information changes the direction.

## Rules

- Do not read logs or source code unless explicitly asked or the saved state calls for it.
- Do not re-expand scope unless new evidence justifies it.
- Focus on validating or eliminating the top hypothesis and executing the saved `Next Step`.
