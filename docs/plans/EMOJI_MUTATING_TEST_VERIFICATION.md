# Emoji Verification in Mutating Functional Tests — Design Spec

Status: locked for implementation. Follow-up to `docs/plans/EMOJI_PICKER.md`
(already implemented, PR #57, not yet merged). That PR added non-mutating
emoji coverage only (text-injection round-trip on Fansly, mocked adapter
text on Bluesky). This spec extends the **mutating** functional tests — the
ones that publish real content to live production social accounts — so each
one includes an emoji in what it posts and explicitly asserts the emoji
survived the round trip to the live platform.

All decisions below are final. If something here turns out to be false
against the current code (a line has drifted, a helper's signature differs),
make the most locally-consistent choice and note the deviation — do not
invent new verification semantics beyond what's specified.

**This spec produces code only. Do not run any functional test — mutating
or non-mutating. These tests publish real posts to real live social media
accounts; running them is the requester's responsibility, done separately
after reviewing this diff.**

## Scope

Exactly these 7 files, each with `@pytest.mark.mutating` test classes/methods
that call `mutating_post_text()` or `mutating_post_tag()`:

- `tests/functional/test_bluesky_post.py`
- `tests/functional/test_twitter_post.py`
- `tests/functional/test_meta_instagram_post.py`
- `tests/functional/test_meta_threads_post.py`
- `tests/functional/test_meta_facebook_page_post.py`
- `tests/functional/test_webview_fansly.py`
- `tests/functional/test_webview_fetlife.py`

**Do not touch** `tests/functional/test_webview_onlyfans.py` (no mutating
tests exist there; OnlyFans functional coverage is out of scope generally)
or `tests/functional/test_webview_snapchat.py` (module carries
`disabled_platform`, no mutating tests exist there).

Do not touch any non-mutating test in these 7 files, and do not touch any
length/character-cap test (`test_status_composer_cap_agrees_with_specs`,
`test_picture_caption_capacity`, `test_video_caption_capacity`,
`test_composer_elements_present`, or any `test_*_too_long_rejected` /
`test_character_limit_enforcement`) — none of those use
`mutating_post_text()`, all use synthetic `'x' * N` strings, and must stay
that way.

## Shared emoji constant

In `tests/functional/conftest.py`, add one module-level constant next to
`mutating_post_tag`/`mutating_post_text`:

```python
MUTATING_TEST_EMOJI = '\U0001F600'  # 😀 — fixed marker for live-post emoji verification
```

Every file in scope imports and uses this single constant — do not invent a
different emoji per platform or hardcode the literal character anywhere
else. Using one fixed, simple (non-ZWJ, non-skin-tone) codepoint keeps the
live-run behavior predictable; ZWJ/skin-tone sequence coverage already
exists in the non-mutating Fansly test from PR #57 and is out of scope here.

## Per-call-site change

At every `mutating_post_text()` call site in the 7 files (30 call sites),
append `MUTATING_TEST_EMOJI` as the **last** positional part:

- `mutating_post_text()` → `mutating_post_text(MUTATING_TEST_EMOJI)`
- The one exception: `test_bluesky_post.py::TestBlueskyTextPost::test_post_with_url_facets`
  currently calls `mutating_post_text('https://example.com')`. Change this to
  `mutating_post_text('https://example.com', MUTATING_TEST_EMOJI)` — the
  emoji **must** come after the URL, not before. This test's real purpose is
  proving Bluesky's link-facet byte-offset detection survives round-trip;
  putting the emoji before the URL would perturb the UTF-8 byte offsets the
  facet assertion depends on, which is not what's under test here.

Do not touch `mutating_post_tag()` calls that exist independent of
`mutating_post_text()` (there are none outside the pattern documented above,
but if one is found, leave it as-is — it's not building post content).

## Per-file verification changes

Two distinct patterns, do not mix them up:

### API platforms (Bluesky, Twitter, Instagram, Threads, Facebook Page) — 26 tests

Each file has one shared `_assert_*_published(...)` style helper
(`_assert_post_published`, `_assert_tweet_published`, `_assert_media_published`
— exact name varies per file) that every mutating test in that file calls.
That helper currently does `tag = post_tag(text)` then
`assert tag in <read-back field>`. **Leave that existing tag assertion
exactly as it is — do not weaken, remove, or replace it.**

Add one new, separate assertion immediately alongside it, checking the fixed
emoji glyph is present in the same read-back field the tag check already
uses:

```python
assert MUTATING_TEST_EMOJI in <same read-back field>, (
    f'{platform_name} did not preserve the emoji in the published text: <field>!r'
)
```

Concretely, per file, the read-back field to check (the same field the
existing `tag in ...` assertion already checks):
- Bluesky (`_assert_post_published`): `post_view.record.text`
- Twitter (`_assert_tweet_published`): `tweet.text`
- Instagram (`_assert_media_published`): `payload.get('caption') or ''`
- Threads (`_assert_post_published`): `payload.get('text') or ''`
- Facebook Page (`_assert_post_published`): `published_text` (already
  resolved from either `message` or `description` depending on post type —
  reuse the same local variable the existing tag assertion uses, do not
  re-derive it)

Add this new assertion **inside the shared helper function**, not duplicated
in each of the 26 call sites — one new line per file's helper covers every
test in that file, matching how the existing tag check already works.

Note the Facebook Page video test (`TestMetaFacebookPageVideoPost.test_video_post`)
uses a local variable named `description`, not `caption`/`text` — this
doesn't change the helper-level fix above, but don't let a mechanical
find/replace across files rename it or miss it.

For `test_post_with_url_facets` specifically: the new emoji assertion comes
from the shared helper as above (no special-casing needed there); the
existing `published_links == ['https://example.com']` facet assertion is
untouched.

### WebView platforms (Fansly, FetLife) — 6 tests

Here the local variable (`tag` in most cases, `test_text` in
`TestFanslyTextInjection`/`TestFetLifeTextPost`) already holds the **full**
`mutating_post_text()` output — there is no separate `post_tag()` reduction
happening for the existing checks (unlike the API platforms above). Once the
emoji is folded into that string via the call-site change, the existing
`tag in <readback>` / `test_text in <readback>` checks already implicitly
require the emoji to survive. Do not rely on that implicitly — add one
explicit, separate assertion at each of the 6 mutating test methods for
auditability and consistency with the API-platform tests above:

```python
assert MUTATING_TEST_EMOJI in <same readback value the existing check uses>, (
    f'Fansly/FetLife did not preserve the emoji: <value>!r'
)
```

Six methods, six explicit assertions (not a shared helper — these tests
don't share one the way the API platforms do):

1. `test_webview_fansly.py::TestFanslyPost::test_text_post_creates_a_post` —
   check against the same value the existing `posted = _wait_for_post(page, tag)`
   check confirms is `found` (add the emoji assertion against `injected.get('value', '')`,
   the composer read-back, right after the existing composer-text assertion).
2. `test_webview_fansly.py::TestFanslyPost::test_image_post_creates_a_post_with_media` —
   same pattern, against `injected.get('value', '')`.
3. `test_webview_fansly.py::TestFanslyPost::test_video_post_creates_a_post_with_media` —
   same pattern, against `injected.get('value', '')`.
4. `test_webview_fetlife.py::TestFetLifeTextPost::test_text_post_submit_and_delete` —
   against `inject_check.get('content', '')`.
5. `test_webview_fetlife.py::TestFetLifePicturePost::test_picture_upload_creates_a_post` —
   against `caption.get('caption') or ''`.
6. `test_webview_fetlife.py::TestFetLifeVideoPost::test_video_upload_creates_a_post` —
   against `caption.get('caption') or ''` (the description field) **and** a
   second assertion against `caption.get('title')` (the title field, since
   `_inject_media_caption` sets both from the same source string — see the
   existing `test_video_attach_via_picker` pattern at
   `test_webview_fetlife.py:1189-1191` for how title equality is already
   checked elsewhere in this file).

## Non-goals

- Do not modify `assert_neutral_live_text`, `post_tag`, `finish_mutating_artifact`,
  or the artifact ledger mechanism in `functional_cleanup.py`.
- Do not add emoji to any non-mutating test.
- Do not change `--leave-mutating-artifacts` behavior or any cleanup logic.
- Do not touch OnlyFans or Snapchat files.
- Do not run `make lint`/`make test-cov` yourself if that's inconvenient in
  your sandbox — the requester will re-verify independently either way — but
  if you can run them, do, and report the result.
- Do not run any functional test, mutating or non-mutating, under any
  circumstance. Do not attempt a "dry run" against the composer or any live
  session. This is a hard constraint, not a preference.

## Acceptance criteria

1. All 30 `mutating_post_text()` call sites in the 7 in-scope files pass
   `MUTATING_TEST_EMOJI` as their last positional part (URL-facet test:
   emoji after the URL).
2. Each of the 5 API-platform `_assert_*_published`-style helpers gains one
   new emoji-presence assertion alongside its existing tag assertion,
   checking the same read-back field, without weakening the existing check.
3. Each of the 6 WebView mutating test methods gains one explicit
   emoji-presence assertion (FetLife video test: two, covering both
   description and title fields).
4. No change to any file outside the 7 listed plus `tests/functional/conftest.py`
   (for the new constant).
5. `make lint` passes.
6. `make test-cov` (non-functional unit suite) passes with no regressions —
   these changes are functional-test-only so this should be a no-op check,
   but confirm nothing else broke.
