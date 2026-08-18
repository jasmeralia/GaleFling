# Vendored icon assets

## `brands/` — Simple Icons

Source: https://github.com/simple-icons/simple-icons (official repo)
License: CC0 1.0 Universal — public domain, no attribution required (`LICENSE-simple-icons.md`)

- `bluesky.svg`, `instagram.svg`, `threads.svg`, `facebook.svg` — current `develop` branch.
- `twitter.svg` — Simple Icons removed the classic bird mark when the platform rebranded
  to X (PR [simple-icons/simple-icons#9748](https://github.com/simple-icons/simple-icons/pull/9748)).
  GaleFling refers to this platform as "Twitter" throughout (never "X" — see AGENTS.md rule 14),
  so this file is vendored from the last commit before that removal
  (`06deb20e92a8d6bc4d51164c31522ca034be2917`) to keep the mark and the label consistent.

FetLife has no mark in Simple Icons — the UI falls back to a plain monogram badge in FetLife's
brand red, drawn in code (no SVG asset).

## `ui/` — Material Symbols

Source: https://github.com/google/material-design-icons (official repo), `materialsymbolsoutlined` set
License: Apache License 2.0 — attribution-friendly, commercial use OK (`LICENSE-material-symbols.txt`)

29 outline glyphs used across the composer toolbar, emoji-picker category rail, settings sidebar,
setup wizard, and results dialog.
