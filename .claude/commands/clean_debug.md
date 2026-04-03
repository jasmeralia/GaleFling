Reduce the size of `debug_state.md` while preserving all live reasoning state.

## Steps

1. Read `debug_state.md` from the project root.
2. Rewrite it for compactness and clarity:
   - Remove stale, superseded, or low-value evidence.
   - Remove dead-end or invalidated hypotheses.
   - Merge redundant or overlapping hypotheses.
   - Tighten prose throughout.
3. Overwrite `debug_state.md` with the cleaned version.
4. Return the full cleaned file contents.

## Rules

- Preserve: current issue summary, active hypotheses, high-value evidence, next step.
- Do not remove any hypothesis that has not been explicitly ruled out.
- Keep the file high-signal and concise — it should be scannable at a glance.
