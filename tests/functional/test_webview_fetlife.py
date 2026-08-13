"""Functional tests for FetLife WebView posting.

Exercises the shipped ``FetLifePlatform`` adapter for text, picture, and video
composers: ``_inject_text()``, ``_attach_media()``, ``_inject_media_caption()``, and
``_certify_upload_consent()``.

**Media upload** is covered at two levels. The non-mutating attach tests load a file
into the composer form and never click Upload. The mutating tests submit for real and
then assert the *published* artifact carries media — not that a URL changed, and not
that the caption alone reached a page. A post created while the upload is still in
flight keeps its caption and silently drops the file, so the caption is evidence that
something was published, never that the media landed. This is the same post-condition
the Fansly suite settled on; see ``docs/platforms/FANSLY.md`` → "Video posts render as
poster images in the feed" for where the rule came from.

``_certify_upload_consent()`` selects the certification field by exact name, so
``picture[is_avatar]`` can never be toggled; the attach test asserts that directly.
"""

from __future__ import annotations

import json
import re

import pytest

from src.platforms.fetlife import FetLifePlatform
from tests.functional.conftest import fail_or_skip, mutating_post_tag, mutating_post_text
from tests.functional.webview_helpers import (
    call_platform,
    close_webview,
    create_webview,
    element_center_js,
    get_or_create_app,
    has_cookie_db,
    load_page,
    login_fetlife,
    run_js,
    trusted_click_at,
    wait_for_attachment,
    wait_ms,
)

ACCOUNT_ID = 'fetlife_1'
TEXT_COMPOSER_URL = FetLifePlatform.TEXT_COMPOSER_URL
IMAGE_COMPOSER_URL = FetLifePlatform.IMAGE_COMPOSER_URL
VIDEO_COMPOSER_URL = FetLifePlatform.VIDEO_COMPOSER_URL
PICTURE_FILE_SELECTOR = FetLifePlatform.IMAGE_FILE_SELECTOR
VIDEO_FILE_SELECTOR = FetLifePlatform.VIDEO_FILE_SELECTOR

# FetLife permalinks are username-scoped (/<username>/pictures/<id>, /<username>/s/<id>).
POST_URL_PATTERN = re.compile(FetLifePlatform.SUCCESS_URL_PATTERN, re.IGNORECASE)


def _maybe_later_prompt_present(page) -> bool:
    """Whether FetLife's recurring "Maybe later" prompt is still on screen.

    The prompt is dismissed by shipped code — ``dismissMaybeLater()`` inside
    ``FetLifePlatform._inject_checkbox_fix()``, driven by a MutationObserver. Tests
    therefore *observe* it rather than dismissing it themselves: a test-side dismissal
    would keep passing even if the shipped one broke, which is the defect class Phase 5
    exists to catch.
    """
    return bool(
        run_js(
            page,
            """
            (function() {
                return Array.from(
                    document.querySelectorAll('button, a, [role="button"]')
                ).some(function(el) {
                    if ((el.textContent || '').trim().toLowerCase() !== 'maybe later') {
                        return false;
                    }
                    var style = window.getComputedStyle(el);
                    return style.display !== 'none' && style.visibility !== 'hidden';
                });
            })();
            """,
        )
    )


def _read_status_text(page) -> dict:
    """Read the status composer textarea after platform text injection."""
    return run_js(
        page,
        f"""
        (function() {{
            var box = document.querySelector({json.dumps(FetLifePlatform.TEXT_SELECTOR)});
            if (!box) return {{found: false}};
            var say = Array.from(document.querySelectorAll('button, input[type="submit"]'))
                .find(function(b) {{
                    return ((b.textContent || b.value || '').trim()
                        === {json.dumps(FetLifePlatform.TEXT_SUBMIT_LABEL)});
                }});
            return {{
                found: true,
                content: box.value.substring(0, 200),
                submitFound: !!say,
                submitDisabled: say ? !!say.disabled : null
            }};
        }})();
        """,
    )


def _status_exists_in_feed(page, tag: str) -> dict:
    """Whether a status carrying *tag* is present on the current page."""
    return run_js(
        page,
        f"""
        (function() {{
            var body = document.body ? document.body.innerText : '';
            var idx = body.indexOf({json.dumps(tag)});
            return {{
                found: idx !== -1,
                url: location.href,
                context: idx === -1 ? null
                    : body.substring(Math.max(0, idx - 60), idx + 60)
            }};
        }})();
        """,
        timeout_ms=10000,
    )


# Media that belongs to the page furniture rather than to a post. FetLife renders the
# author's avatar inside the same container as the upload, so an unfiltered "is there
# an <img>?" check reports success on a post whose picture silently dropped — the
# exact false pass the Fansly suite hit and fixed (docs/platforms/FANSLY.md).
_CHROME_MEDIA_JS = """
function chrome(m) {
    if (m.closest('header, nav, footer, aside')) return true;
    if (/avatar|profile-pic|user-pic|logo/i.test((m.className || '') + ' ' + (m.id || ''))) {
        return true;
    }
    if (m.closest('[class*="avatar"], [class*="user-info"], [class*="author"]')) return true;
    var r = m.getBoundingClientRect();
    // A zero-size element is not rendered, so it is not evidence that media landed.
    //
    // This branch previously read `r.width > 0 && r.width <= 120 ...`, which let every
    // unrendered element through as media. Measured against a real published picture on
    // 2026-08-12: the post reported four "media" items, three of them 0x0 — one being
    // the author avatar (`ipp size-14 ...`, Tailwind 56px, measuring 0x0 because it had
    // not been laid out). It carries a real src and no "avatar" in its class name, so
    // every other rule here missed it too. Had the upload silently dropped, hasMedia
    // would still have been true from that avatar alone — the precise false pass this
    // function exists to prevent.
    if (r.width <= 0 || r.height <= 0) return true;
    // FetLife's avatars are square thumbnails; uploaded media renders far larger.
    return r.width <= 120 && r.height <= 120;
}
"""


def _published_media_report(page, tag: str) -> dict:
    """Whether the published item carrying *tag* actually renders media.

    Scoped to the container that owns the tag — an ``<article>`` in a feed or gallery,
    else the document on a permalink page, where the whole page *is* the post. Walking
    up until an image turns up instead would escape into the surrounding feed and find
    somebody else's picture, which is how the Fansly equivalent first passed wrongly.

    Returns the matched media's tag, classes and dimensions so a pass can be audited
    rather than taken on trust: "hasMedia: true" with a 40x40 match is an avatar that
    slipped the filter, and that is visible in the printed result.
    """
    return run_js(
        page,
        f"""
        (function() {{
            {_CHROME_MEDIA_JS}
            var leaf = Array.from(document.querySelectorAll('*')).filter(function(el) {{
                return el.children.length === 0
                    && (el.textContent || '').indexOf({json.dumps(tag)}) !== -1;
            }})[0];
            if (!leaf) return {{found: false, reason: 'tag not on page', url: location.href}};

            // On a permalink the page is the post; in a feed or gallery it is the
            // enclosing article. Never climb past either.
            var scope = leaf.closest('article');
            var scoped = !!scope;
            if (!scope) {{
                if (/\\/(pictures|videos|s)\\/\\d+/.test(location.pathname)) {{
                    scope = document.body;
                }} else {{
                    return {{
                        found: true, hasMedia: false,
                        reason: 'no article ancestor and not on a permalink',
                        url: location.href
                    }};
                }}
            }}

            function sourced(m) {{
                if (/^https?:|^blob:/.test(m.src || m.currentSrc || '')) return true;
                if (m.tagName.toLowerCase() !== 'video') return false;
                // A <video> mid-transcode may carry only its poster, and FetLife puts
                // the real URL on a <source> child. Requiring element.src alone reports
                // "no media" on a perfectly good video.
                if (/^https?:|^blob:/.test(m.getAttribute('poster') || '')) return true;
                return Array.from(m.querySelectorAll('source')).some(function(s) {{
                    return /^https?:|^blob:/.test(s.getAttribute('src') || '');
                }});
            }}

            var media = Array.from(scope.querySelectorAll('img, video')).filter(function(m) {{
                return sourced(m) && !chrome(m);
            }}).map(function(m) {{
                var r = m.getBoundingClientRect();
                return {{
                    tag: m.tagName.toLowerCase(),
                    cls: ((m.className || '') + '').trim().substring(0, 60),
                    w: Math.round(r.width),
                    h: Math.round(r.height)
                }};
            }});

            return {{
                found: true, scopedToArticle: scoped, url: location.href,
                hasMedia: media.length > 0, count: media.length, media: media.slice(0, 4)
            }};
        }})();
        """,
        timeout_ms=15000,
    )


def _ensure_session(page, credentials: dict) -> None:
    """Verify we have a valid FetLife session, logging in if needed."""
    ok, final_url = load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
    if not ok:
        wait_ms(2000)
        ok, final_url = load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
    if not ok:
        fail_or_skip(f'FetLife page load failed: {final_url}')

    if '/login' in final_url.lower():
        success = login_fetlife(page, credentials['email'], credentials['password'])
        if not success:
            fail_or_skip('FetLife login failed — check credentials in .env')
        ok, final_url = load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
        if not ok or '/login' in final_url.lower():
            fail_or_skip('FetLife composer unreachable after login')
    wait_ms(1000)  # let the shipped MutationObserver dismiss the recurring prompt
    assert not _maybe_later_prompt_present(page), (
        'FetLife "Maybe later" prompt is still showing — the shipped '
        'dismissMaybeLater() in FetLifePlatform._inject_checkbox_fix() did not fire'
    )


def _read_media_caption(page, is_video: bool) -> dict:
    """Read back the caption (and video title) actually sitting in the upload form.

    ``_inject_media_caption()`` returns ``{caption: true}`` whenever the field *exists*
    — its inner ``fill()`` reports that it found an element, not that the value stuck.
    Asserting on that return is therefore the same class of false pass as clicking a
    disabled ``<div>`` and calling it a submit: it cannot fail for the reason it is
    being checked. Read the DOM instead.
    """
    caption_selector = (
        FetLifePlatform.VIDEO_CAPTION_SELECTOR
        if is_video
        else FetLifePlatform.IMAGE_CAPTION_SELECTOR
    )
    return run_js(
        page,
        f"""
        (function() {{
            var caption = document.querySelector({json.dumps(caption_selector)});
            var title = {json.dumps(is_video)}
                ? document.querySelector({json.dumps(FetLifePlatform.VIDEO_TITLE_SELECTOR)})
                : null;
            return {{
                captionFound: !!caption,
                caption: caption ? caption.value.substring(0, 200) : null,
                titleFound: !!title,
                title: title ? title.value.substring(0, 120) : null
            }};
        }})();
        """,
    )


def _caption_capacity(page, platform, is_video: bool, lengths: list[int]) -> dict:
    """Measure how much text the open composer's caption field actually retains.

    The media composers show no character counter, so their limit is not observable
    the way the status composer's 690 is — it has to be probed. For each length, the
    text is injected through shipped ``_inject_media_caption()`` and read straight back
    out of the DOM; a field that silently truncates reports a shorter ``kept``.

    Also reports ``maxlength``, which would settle the question outright if FetLife
    sets one, and whether the field is a ``textarea`` (no attribute-level cap implied).
    """
    caption_selector = (
        FetLifePlatform.VIDEO_CAPTION_SELECTOR
        if is_video
        else FetLifePlatform.IMAGE_CAPTION_SELECTOR
    )
    attrs = run_js(
        page,
        f"""
        (function() {{
            var el = document.querySelector({json.dumps(caption_selector)});
            if (!el) return {{found: false}};
            return {{
                found: true,
                tag: el.tagName.toLowerCase(),
                maxlength: el.getAttribute('maxlength'),
                name: el.getAttribute('name')
            }};
        }})();
        """,
    )
    observed = []
    for length in lengths:
        call_platform(platform._inject_media_caption, 'x' * length)
        wait_ms(400)
        kept = run_js(
            page,
            f"""
            (function() {{
                var el = document.querySelector({json.dumps(caption_selector)});
                return el ? el.value.length : -1;
            }})();
            """,
        )
        observed.append({'sent': length, 'kept': kept})
    return {'attrs': attrs, 'observed': observed}


def _composer_elements(page, file_selector: str, submit_label: str) -> dict:
    """Report the file input and upload button on an open upload composer."""
    return run_js(
        page,
        f"""
        (function() {{
            var fileInput = document.querySelector({json.dumps(file_selector)});
            var submitBtn = Array.from(
                document.querySelectorAll('button[type="submit"]')
            ).find(function(b) {{
                return b.textContent.includes({json.dumps(submit_label)});
            }});
            var attachControl = Array.from(document.querySelectorAll('button')).filter(
                function(b) {{
                    return (b.textContent || '').trim() === 'Choose File';
                }}
            )[0];
            var attachRect = attachControl ? attachControl.getBoundingClientRect() : null;
            return {{
                fileInputFound: !!fileInput,
                fileInputAccept: fileInput ? fileInput.accept : null,
                submitFound: !!submitBtn,
                submitDisabled: submitBtn ? submitBtn.disabled : null,
                attachControlVisible: !!(
                    attachRect && attachRect.width > 0 && attachRect.height > 0
                )
            }};
        }})();
        """,
    )


def _upload_form_state(page, composer_path: str) -> dict:
    """Report where an attached file landed and whether any side-effect box was set."""
    return run_js(
        page,
        f"""
        (function() {{
            var named = document.querySelector(
                'input[type="file"][name="picture[attachments][]"]'
            );
            var avatar = document.querySelector(
                'input[type="checkbox"][name="picture[is_avatar]"]'
            );
            var total = 0;
            document.querySelectorAll('input[type="file"]').forEach(function(el) {{
                if (el.files) total += el.files.length;
            }});
            return {{
                stillOnComposer: window.location.href.includes({json.dumps(composer_path)}),
                totalFiles: total,
                namedFieldFiles: named && named.files ? named.files.length : 0,
                avatarChecked: avatar ? avatar.checked : false
            }};
        }})();
        """,
    )


# The article that owns *tag*, as a JS expression. The tag text sits in a leaf several
# levels below the article and only the article carries the controls, so walking to the
# deepest node containing the tag finds an element with no controls at all. Scoping to
# the article is also what stops any other status being deleted.
def _tagged_article_js(tag: str) -> str:
    # Scoped to document.body deliberately. FetLife puts the status text in the page
    # <title> as well, so an unscoped '*' search matches the <title> element first —
    # measured on the permalink page, where the leaf's ancestor chain came back as
    # title > head > html and closest('article') was therefore null.
    return f"""
    (function() {{
        var root = document.body;
        if (!root) return null;
        var leaf = Array.from(root.querySelectorAll('*')).filter(function(el) {{
            return el.children.length === 0
                && (el.textContent || '').indexOf({json.dumps(tag)}) !== -1;
        }})[0];
        return leaf ? leaf.closest('article') : null;
    }})()
    """


def _control_in_article_js(tag: str, label: str) -> str:
    """A control inside *tag*'s article whose text is exactly *label*, as a JS expression.

    Exact match, never a substring: FetLife's overflow menu puts "Delete" directly
    beside Edit, Copy Link and "Who can Comment?", and a keyword match over a menu of
    destructive actions is the same hazard as the ``picture[is_avatar]`` checkbox next
    to the consent one.

    Entries are ``<a class="dropdown-menu-entry" href="#0">`` and measure 0x0 until the
    menu is open, so the visibility test doubles as "the menu actually opened".
    """
    return f"""
    (function() {{
        var host = {_tagged_article_js(tag)};
        if (!host) return null;
        return Array.from(host.querySelectorAll('a, button, [role="button"]')).filter(
            function(c) {{
                if ((c.textContent || '').trim().toLowerCase() !== {json.dumps(label.lower())}) {{
                    return false;
                }}
                var r = c.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }}
        )[0] || null;
    }})()
    """


def _titled_control_in_article_js(tag: str, title: str) -> str:
    """A control inside *tag*'s article whose ``title`` attribute is exactly *title*.

    The overflow control that opens the status menu is **icon-only**: an
    ``<a href="#0">`` wrapping an ``<svg>``, with empty ``textContent`` and its label
    carried in ``title="More options"``. Measured live 2026-08-12 — this is why matching
    on text alone found nothing, and why the status delete silently never started.
    """
    return f"""
    (function() {{
        var host = {_tagged_article_js(tag)};
        if (!host) return null;
        return Array.from(host.querySelectorAll('[title]')).filter(function(c) {{
            if ((c.getAttribute('title') || '').trim().toLowerCase()
                    !== {json.dumps(title.lower())}) {{
                return false;
            }}
            var r = c.getBoundingClientRect();
            return r.width > 0 && r.height > 0;
        }})[0] || null;
    }})()
    """


# The confirmation dialog's affirmative control, as a JS expression.
#
# Scoped to a **visible** modal footer, which is the whole point. The previous shared
# helper scoped with
#     document.querySelector('[role="dialog"], ..., .modal, dialog[open], ...')
# and applied no visibility test, so on FetLife it latched onto the account sidebar —
# an <aside role="dialog"> that is invisible and sits earlier in document order than
# the modal. It then searched that empty drawer and reported `scoped: true` with no
# button found, which read as "the dialog had no delete button" rather than "we were
# looking in the wrong element entirely". Measured live 2026-08-12.
#
# Both controls in the footer are <button type="submit"> — Cancel and "Delete Status
# Update" — so the type carries no signal and the label is the only discriminator.
# Cancel is excluded by name as well as by the affirmative prefix, because clicking it
# would silently abandon cleanup while every later check still passed.
_CONFIRM_DELETE_CONTROL_JS = """
(function() {
    function shown(el) {
        var r = el.getBoundingClientRect();
        var s = getComputedStyle(el);
        return r.width > 0 && r.height > 0
            && s.display !== 'none' && s.visibility !== 'hidden';
    }
    var footer = Array.from(document.querySelectorAll(
        'footer.qa-modal-footer, [class*="modal-footer"]'
    )).filter(shown)[0];
    if (!footer) return null;
    return Array.from(footer.querySelectorAll('button, [role="button"]')).filter(
        function(el) {
            if (!shown(el)) return false;
            var label = (el.textContent || el.value || '').trim().toLowerCase();
            if (label === 'cancel') return false;
            return label.indexOf('delete') === 0;
        }
    )[0] || null;
})()
"""


def _delete_status_by_tag(view, page, tag: str) -> dict:
    """Delete the feed status carrying *tag* via its own dropdown Delete entry.

    **Why this needs real mouse events.** Investigated against a live status on
    2026-08-11: the Delete entry is an ``<a href="#0">`` whose only payload is a ``data``
    attribute that stringifies to ``[object Object]`` — no ``data-method``, no
    ``data-turbo-confirm``, no delete endpoint. The handler is bound in JavaScript, so a
    synthetic ``.click()`` never reaches it and no confirmation dialog is raised, which
    is why the JS-only version of this helper could never work.

    A trusted mouse event at the element's viewport coordinates is what reaches it, the
    same mechanism the Fansly media flow needed for its dropdown. The overflow menu must
    be opened first: the Delete entry measures 0x0 until it is on screen.

    **The overflow control is matched by ``title``, not by text.** It is icon-only —
    ``<a href="#0">`` around an ``<svg>``, empty ``textContent``,
    ``title="More options"``. An earlier version matched on text and so never found it,
    then fell back to "the article's last visible button". That fallback was both
    useless and unsafe: the article contains no ``<button>`` at all (every control is an
    ``<a>``), and had it matched anything it would have been Bookmark or Share — real
    side effects on a live account. There is deliberately no fallback now; an unfound
    control is reported.

    ``deleted`` reflects the status actually leaving the feed on a fresh page load —
    never that a control was clicked. Cleanup that silently did nothing must not report
    success, or a stray live post goes unnoticed.
    """
    point = element_center_js(page, _titled_control_in_article_js(tag, 'More options'))
    if point is None:
        return {
            'deleted': False,
            'reason': 'no [title="More options"] control on the status article',
        }
    trusted_click_at(view, *point)

    delete_point = element_center_js(page, _control_in_article_js(tag, 'delete'))
    if delete_point is None:
        return {'deleted': False, 'reason': 'Delete entry never became visible'}
    trusted_click_at(view, *delete_point)

    wait_ms(2000)
    confirm_point = element_center_js(page, _CONFIRM_DELETE_CONTROL_JS)
    if confirm_point is None:
        return {'deleted': False, 'reason': 'delete confirmation control not found'}
    trusted_click_at(view, *confirm_point)
    wait_ms(2500)

    # Only the status leaving the feed counts as deleted.
    load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
    wait_ms(3000)
    gone = not _status_exists_in_feed(page, tag).get('found')
    return {'deleted': gone}


def _own_profile_href(page) -> str | None:
    """Resolve the logged-in account's profile path (e.g. /Jasmeralia)."""
    return run_js(
        page,
        """
        (function() {
            var a = Array.from(document.querySelectorAll('a[href^="/"]')).find(function(x) {
                return /view profile/i.test(x.textContent || '');
            });
            return a ? a.getAttribute('href').split('?')[0] : null;
        })();
        """,
        timeout_ms=10000,
    )


def _wait_for_media_in_gallery(page, kind: str, tag: str, timeout_ms: int = 180000) -> dict:
    """Poll the account's own gallery until media carrying *tag* appears.

    Uploads are asynchronous — FetLife stays on the composer while the file transfers
    and transcodes — so the composer URL never changes and cannot signal success.
    """
    profile = _own_profile_href(page)
    if not profile:
        load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
        wait_ms(2500)
        profile = _own_profile_href(page)
    if not profile:
        return {'found': False, 'reason': 'could not resolve own profile path'}

    gallery = f'https://fetlife.com{profile}/{kind}'
    elapsed = 0
    while elapsed <= timeout_ms:
        load_page(page, gallery, timeout_ms=25000)
        wait_ms(3000)
        hit = _status_exists_in_feed(page, tag)
        if hit.get('found'):
            return {'found': True, 'gallery': gallery, 'context': hit.get('context')}
        wait_ms(7000)
        elapsed += 10000
    return {'found': False, 'gallery': gallery, 'waited_ms': elapsed}


def _wait_for_enabled_submit(page, label: str, timeout_ms: int = 60000) -> dict:
    """Poll until an exactly-labelled submit button is enabled, then click it.

    Both upload buttons start disabled and enable only once the form is satisfied
    (file attached, consent certified), so clicking immediately does nothing.
    """
    elapsed = 0
    status: dict = {}
    while elapsed <= timeout_ms:
        status = run_js(
            page,
            f"""
            (function() {{
                var btn = Array.from(document.querySelectorAll(
                    'button[type="submit"], input[type="submit"]'
                )).find(function(b) {{
                    return (b.textContent || b.value || '').trim()
                        .indexOf({json.dumps(label)}) === 0;
                }});
                return {{
                    found: !!btn,
                    disabled: btn ? !!btn.disabled : null
                }};
            }})();
            """,
        )
        if isinstance(status, dict) and status.get('found') and not status.get('disabled'):
            return _click_submit_button(page, label)
        wait_ms(1500)
        elapsed += 1500
    return {'clicked': False, 'reason': 'submit stayed disabled', 'detail': status}


def _avatar_checkbox_state(page) -> dict:
    """Report picture[is_avatar] — it must never be set by GaleFling or its tests."""
    return run_js(
        page,
        f"""
        (function() {{
            var cb = document.querySelector({json.dumps(FetLifePlatform.AVATAR_CHECKBOX_SELECTOR)});
            return {{present: !!cb, checked: cb ? !!cb.checked : false}};
        }})();
        """,
    )


def _click_submit_button(page, label_fragments: str | list[str]) -> dict:
    """Click a submit control matching one of *label_fragments* (case-insensitive)."""
    if isinstance(label_fragments, str):
        fragments = [label_fragments]
    else:
        fragments = label_fragments
    return run_js(
        page,
        f"""
        (function() {{
            var needles = {json.dumps([f.lower() for f in fragments])};
            var controls = Array.from(document.querySelectorAll(
                'button[type="submit"], input[type="submit"], button, [role="button"]'
            ));
            var btn = controls.find(function(el) {{
                var label = (el.textContent || el.value || '').trim().toLowerCase();
                return needles.some(function(needle) {{ return label.includes(needle); }});
            }});
            if (!btn) {{
                return {{
                    clicked: false,
                    reason: 'Button not found',
                    labels: controls.slice(0, 8).map(function(el) {{
                        return (el.textContent || el.value || '').trim();
                    }}).filter(Boolean)
                }};
            }}
            if (btn.disabled) return {{clicked: false, reason: 'Button disabled'}};
            btn.click();
            return {{
                clicked: true,
                label: (btn.textContent || btn.value || '').trim()
            }};
        }})();
        """,
    )


@pytest.mark.functional
@pytest.mark.non_mutating
class TestFetLifeConnection:
    """Session and platform adapter checks — fail fast before posting tests."""

    def test_has_valid_session(self, galefling_data_dir):
        """Cookie database must exist and pass has_valid_session()."""
        if not has_cookie_db(galefling_data_dir, ACCOUNT_ID):
            pytest.skip('No FetLife cookie database — log in via Settings first')
        platform = FetLifePlatform(account_id=ACCOUNT_ID)
        assert platform.has_valid_session(), 'FetLife session invalid or expired'

    def test_authenticate(self, galefling_data_dir):
        """WebView platforms report authenticate() success when cookies exist."""
        if not has_cookie_db(galefling_data_dir, ACCOUNT_ID):
            pytest.skip('No FetLife cookie database')
        platform = FetLifePlatform(account_id=ACCOUNT_ID)
        ok, err = platform.authenticate()
        assert ok, f'authenticate() failed: {err}'
        assert err is None

    def test_connection(self, galefling_data_dir, fetlife_credentials):
        """Platform test_connection() after loading the shared WebView profile."""
        if not has_cookie_db(galefling_data_dir, ACCOUNT_ID):
            pytest.skip('No FetLife cookie database')
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            ok, err = platform.test_connection()
            if not ok and err == 'WV-SESSION-EXPIRED':
                _ensure_session(page, fetlife_credentials)
                ok, err = platform.test_connection()
            assert ok, f'test_connection() failed: {err}'
            assert err is None
        finally:
            close_webview(view, page, platform)

    def test_composer_url_routing(self, tmp_path):
        """get_composer_url() must route text, image, and video composers."""
        platform = FetLifePlatform(account_id=ACCOUNT_ID)
        assert platform.get_composer_url() == TEXT_COMPOSER_URL

        platform._image_path = tmp_path / 'photo.jpg'
        assert platform.get_composer_url() == IMAGE_COMPOSER_URL

        platform._image_path = tmp_path / 'clip.mp4'
        assert platform.get_composer_url() == VIDEO_COMPOSER_URL


@pytest.mark.functional
class TestFetLifeTextPost:
    """FetLife text post via FetLifePlatform._inject_text()."""

    @pytest.mark.non_mutating
    def test_composer_loads(self, galefling_data_dir, fetlife_credentials):
        """Verify the text composer page loads in an authenticated state."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            final_url = page.url().toString()
            assert '/login' not in final_url.lower(), f'Redirected to login: {final_url}'

            composer = _read_status_text(page)
            assert composer.get('found'), f'Status composer textarea not found: {composer}'
            assert composer.get('submitFound'), (
                f'"{FetLifePlatform.TEXT_SUBMIT_LABEL}" button not found: {composer}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.non_mutating
    def test_text_injection_via_platform(self, galefling_data_dir, fetlife_credentials):
        """Verify FetLifePlatform._inject_text() fills the Lexxy editor."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            wait_ms(2000)

            test_text = mutating_post_tag()
            platform._inject_text(test_text)
            wait_ms(500)

            result = _read_status_text(page)
            assert isinstance(result, dict), f'JS returned: {result}'
            assert result.get('found'), 'Lexxy editor not found'
            assert test_text in result.get('content', ''), f'Text not injected: {result}'
        finally:
            close_webview(view, page, platform)

    @pytest.mark.non_mutating
    def test_status_composer_cap_agrees_with_specs(self, galefling_data_dir, fetlife_credentials):
        """The **status** composer must cut off exactly where FETLIFE_SPECS says it does.

        Fansly can assert this against the textarea's ``maxlength``; FetLife sets none,
        and enforces the cap by disabling "Say It!" instead. So the boundary is probed
        the way the limit is actually expressed — at the cap the button is live, one
        character past it the button is dead.

        ``FETLIFE_SPECS.max_text_length = 690`` is well established for *this* composer:
        FetLife displays the number itself, and it has been measured empirically more
        than once. What this test adds is that nothing re-checks it on an ongoing basis,
        and ``main_window`` refuses to send a post longer than it — so if FetLife moved
        the cap down, GaleFling would keep accepting statuses the composer rejects.

        **Scope is text-only posts.** The picture and video composers have their own
        caption fields with no visible counter, and their limits are a separate open
        question — see ``test_picture_caption_capacity``. Do not read a pass here as
        saying anything about captions.

        Never submits: the text is injected and read back only.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            wait_ms(2000)

            cap = platform.get_specs().max_text_length

            platform._inject_text('x' * cap)
            wait_ms(800)
            at_cap = _read_status_text(page)
            assert at_cap.get('submitFound'), f'Submit control missing: {at_cap}'
            assert not at_cap.get('submitDisabled'), (
                f'"{FetLifePlatform.TEXT_SUBMIT_LABEL}" is disabled at {cap} characters — '
                f'FetLife caps statuses lower than FETLIFE_SPECS.max_text_length says: {at_cap}'
            )

            platform._inject_text('x' * (cap + 1))
            wait_ms(800)
            over_cap = _read_status_text(page)
            assert over_cap.get('submitDisabled'), (
                f'"{FetLifePlatform.TEXT_SUBMIT_LABEL}" is still enabled at {cap + 1} '
                f'characters — FetLife accepts more than FETLIFE_SPECS.max_text_length '
                f'says, so GaleFling is truncating statuses it need not: {over_cap}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.mutating
    def test_text_post_submit_and_delete(self, galefling_data_dir, fetlife_credentials):
        """Post a status, prove it exists on the feed, then attempt deletion.

        The post-condition is deliberately the status appearing on the feed, not a URL
        change.  FetLife stays on / returns to the feed either way, so asserting on the
        URL cannot distinguish a published status from a rejected submit — an earlier
        version of this test passed while creating nothing at all.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            wait_ms(3000)

            test_text = mutating_post_text()

            print(f'\n  posting tag {test_text} — delete this if the run fails')
            platform._inject_text(test_text)
            wait_ms(1000)

            inject_check = _read_status_text(page)
            assert inject_check.get('found') and test_text in inject_check.get('content', ''), (
                f'Text injection failed: {inject_check}'
            )
            assert inject_check.get('submitFound'), (
                f'"{FetLifePlatform.TEXT_SUBMIT_LABEL}" button not found: {inject_check}'
            )
            assert not inject_check.get('submitDisabled'), (
                f'"{FetLifePlatform.TEXT_SUBMIT_LABEL}" still disabled after injection — '
                f'the composer did not register the text: {inject_check}'
            )

            submit_result = _click_submit_button(page, FetLifePlatform.TEXT_SUBMIT_LABEL)
            assert isinstance(submit_result, dict) and submit_result.get('clicked'), (
                f'Submit failed: {submit_result}'
            )

            wait_ms(8000)
            posted = _status_exists_in_feed(page, test_text)
            if not posted.get('found'):
                load_page(page, TEXT_COMPOSER_URL, timeout_ms=20000)
                wait_ms(3000)
                posted = _status_exists_in_feed(page, test_text)
            assert posted.get('found'), (
                f'Status {test_text} is not on the feed after submit — nothing was posted: {posted}'
            )

            print(f'\n  FetLife status posted (tag {test_text})')
            # Unconditionally the trusted-click path. This used to branch on the URL
            # matching a permalink and hand off to a JS-click helper, but that branch
            # could not have worked: a status posts in place, so the URL stays on the
            # feed and the branch was never taken — and had it been, FetLife's Delete
            # binds its handler in JavaScript and ignores a synthetic click anyway.
            delete_outcome = _delete_status_by_tag(view, page, test_text)
            print(f'  Delete attempt: {delete_outcome}')
            if not delete_outcome.get('deleted'):
                print(
                    f'  CLEANUP PENDING (leave up until any follow-up inspection is done) — status {test_text} is still on the feed'
                )
        finally:
            close_webview(view, page, platform)


@pytest.mark.functional
class TestFetLifePicturePost:
    """FetLife picture upload via FetLifePlatform._attach_media()."""

    @pytest.mark.non_mutating
    def test_picture_attach_via_picker(self, galefling_data_dir, fetlife_credentials, sample_jpeg):
        """The shipped media pre-fill path must leave the picture form ready.

        This complements the retained base64 helper test below. It enters through
        ``_do_prefill()``, uses the native picker path, and never submits the form.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            ok, final_url = load_page(page, IMAGE_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)
            # Neutral even though this probe never submits: the text still reaches a live
            # composer field on a real account, and a draft that autosaves or a future
            # change that does submit would publish whatever is here.
            caption_text = mutating_post_tag()
            platform.prepare_post(caption_text, [sample_jpeg])
            platform.suppress_native_file_dialog = True
            platform._do_prefill()
            state = wait_for_attachment(platform)
            wait_ms(1500)  # let the sequencer fill caption and certify after attachment
            print(
                f'\n  FetLife picker probe: picker_invocations={platform.picker_invocations}, '
                f'attachment={state}',
                flush=True,
            )
            # Exactly one: a second picker would mean the input fallback fired after
            # the visible control had already opened one, and its empty selection
            # clears the first attachment.
            assert platform.picker_invocations == 1, (
                f'expected one chooseFiles() call, got {platform.picker_invocations}'
            )
            assert state.get('attached'), f'Picture form never retained the file: {state}'
            assert 'picture[attachments][]' in state.get('holders', []), (
                f'File did not reach the named form field: {state}'
            )
            caption = _read_media_caption(page, is_video=False)
            assert caption.get('caption') == caption_text, f'Caption did not stick: {caption}'
            consent = run_js(
                page,
                """
                (function() {
                    var box = document.querySelector(
                        'input[type="checkbox"][name="picture[is_certified]"]'
                    );
                    return {present: !!box, checked: !!(box && box.checked)};
                })();
                """,
            )
            assert consent.get('checked'), f'Consent was not certified: {consent}'
            avatar = _avatar_checkbox_state(page)
            assert avatar.get('present') and not avatar.get('checked'), (
                f'Avatar replacement must stay off: {avatar}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.non_mutating
    def test_picture_composer_loads(self, galefling_data_dir, fetlife_credentials):
        """Verify the picture composer loads with file input, submit button, and consent."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)

            ok, final_url = load_page(page, IMAGE_COMPOSER_URL, timeout_ms=20000)
            assert ok, f'Page load failed: {final_url}'
            assert '/login' not in final_url.lower(), f'Session expired: {final_url}'
            wait_ms(2000)

            result = _composer_elements(
                page, PICTURE_FILE_SELECTOR, FetLifePlatform.IMAGE_SUBMIT_LABEL
            )
            assert isinstance(result, dict), f'JS returned: {result}'
            assert result.get('fileInputFound'), 'File input not found'
            assert result.get('submitFound'), 'Upload button not found'
            assert result.get('attachControlVisible'), (
                f'Visible Choose File control not found: {result}'
            )
            assert 'image' in (result.get('fileInputAccept') or ''), (
                'File input does not accept images'
            )

            consent = call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent certification not set: {consent}'
            assert consent.get('names') == ['picture[is_certified]'], (
                f'Unexpected certification fields: {consent}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.non_mutating
    def test_picture_attach_via_platform(
        self, galefling_data_dir, fetlife_credentials, sample_jpeg
    ):
        """FetLifePlatform._attach_media() must load a file into the picture form.

        The picture composer exposes two file inputs: a hidden picker carrying the
        ``accept`` list, and the real ``picture[attachments][]`` field.  FetLife's own
        JS moves the file from the first to the second and clears the picker, so the
        attach is verified on the form as a whole.  Never submits.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)

            ok, final_url = load_page(page, IMAGE_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)

            platform._image_path = sample_jpeg
            assert platform.get_media_file_selector() == PICTURE_FILE_SELECTOR

            attach = call_platform(platform._attach_media, sample_jpeg)
            assert attach.get('dispatched'), f'Attach failed: {attach}'

            state = wait_for_attachment(platform)
            assert state.get('attached'), f'Form never accepted the file: {state}'
            assert 'picture[attachments][]' in state.get('holders', []), (
                f'File did not reach the named form field: {state}'
            )

            consent = call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent certification not set: {consent}'

            page_state = _upload_form_state(page, 'pictures/new')
            assert page_state.get('stillOnComposer'), 'Must not navigate away without submit'
            assert not page_state.get('avatarChecked'), (
                f'picture[is_avatar] must never be toggled: {page_state}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.non_mutating
    def test_picture_caption_capacity(self, galefling_data_dir, fetlife_credentials):
        """`picture[caption]` must hold at least as much text as GaleFling will send.

        **This is an open question being narrowed, not a known limit being guarded.**
        ``FETLIFE_SPECS.max_text_length = 690`` was established against the *status*
        composer, which displays its own count; the caption field shows no counter and
        its ceiling has never been measured. ``main_window`` applies the single
        ``max_text_length`` to every FetLife post regardless of composer, so the two
        being different matters as soon as captions are wired into the post flow
        (task #417 Level B).

        Only one direction is a defect, so only that direction is asserted: if the
        caption holds *less* than 690, GaleFling will send text FetLife silently
        truncates. Holding more is a missed opportunity, not a bug, and is reported
        rather than failed — the probe results are printed so the real ceiling can be
        read off the run and the specs updated deliberately.

        Never submits, and never attaches a file: the caption field is present on the
        empty composer.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            ok, final_url = load_page(page, IMAGE_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)

            cap = platform.get_specs().max_text_length
            # _inject_media_caption() picks its field from the staged media's suffix;
            # with nothing staged it targets picture[caption], which is what we want.
            assert platform._image_path is None, 'expected an unstaged composer'

            probe = _caption_capacity(page, platform, is_video=False, lengths=[cap, cap * 4])
            print(f'\n  picture caption probe: {probe}', flush=True)

            attrs = probe.get('attrs', {})
            assert attrs.get('found'), (
                f'{FetLifePlatform.IMAGE_CAPTION_SELECTOR} not on the composer: {attrs}'
            )

            at_cap = probe['observed'][0]
            assert at_cap['kept'] == cap, (
                f'picture[caption] holds only {at_cap["kept"]} of {cap} characters — '
                f'FetLife caps captions below FETLIFE_SPECS.max_text_length, so a media '
                f'post at the spec limit would be silently truncated: {probe}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.mutating
    def test_picture_upload_creates_a_post(
        self, galefling_data_dir, fetlife_credentials, sample_jpeg
    ):
        """Upload a real picture and prove the published post carries the image.

        **The post-condition is the picture, not the URL.** This previously asserted
        ``POST_URL_PATTERN.search(url) or caption_found`` — an ``or`` whose left side is
        satisfied by any navigation to any picture permalink, including one that already
        existed. Either branch alone also says nothing about the image: FetLife renders
        the caption from the form field, so a submit that lost the attachment produces a
        page carrying the tag and no picture. Both halves are now required, and the
        image itself is verified.

        Cleanup is manual by decision — the run prints the caption tag.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            ok, final_url = load_page(page, IMAGE_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)

            tag = mutating_post_text()

            print(f'\n  posting tag {tag} — delete this if the run fails')
            platform._image_path = sample_jpeg

            attach = call_platform(platform._attach_media, sample_jpeg)
            assert attach.get('dispatched'), f'Attach failed: {attach}'
            state = wait_for_attachment(platform)
            assert state.get('attached'), f'Form never accepted the file: {state}'

            call_platform(platform._inject_media_caption, tag)
            caption = _read_media_caption(page, is_video=False)
            assert caption.get('captionFound'), (
                f'{FetLifePlatform.IMAGE_CAPTION_SELECTOR} missing: {caption}'
            )
            assert tag in (caption.get('caption') or ''), (
                f'Caption did not stick in the form: {caption}'
            )

            consent = call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent not certified: {consent}'

            avatar = _avatar_checkbox_state(page)
            assert avatar.get('present'), f'Avatar checkbox missing — form changed: {avatar}'
            assert not avatar.get('checked'), (
                'picture[is_avatar] is checked; refusing to submit and replace the account avatar'
            )

            submit = _wait_for_enabled_submit(page, FetLifePlatform.IMAGE_SUBMIT_LABEL)
            assert submit.get('clicked'), f'Upload not clicked: {submit}'

            wait_ms(15000)
            post_url = page.url().toString()
            assert POST_URL_PATTERN.search(post_url), (
                f'Upload did not land on a picture permalink — url={post_url}'
            )
            posted = _status_exists_in_feed(page, tag)
            assert posted.get('found'), (
                f'Picture permalink {post_url} does not carry caption {tag} — this is not '
                f'the post we just created: {posted}'
            )

            media = _published_media_report(page, tag)
            assert media.get('hasMedia'), f'FetLife published the caption but no picture: {media}'
            print(f'\n  FetLife picture uploaded (tag {tag}) -> {post_url}')
            print(f'  media: {media}')
            print(
                f'  CLEANUP PENDING (leave up until any follow-up inspection is done) — delete the picture tagged {tag}'
            )
        finally:
            close_webview(view, page, platform)


@pytest.mark.functional
class TestFetLifeVideoPost:
    """FetLife video upload via FetLifePlatform._attach_media()."""

    @pytest.mark.non_mutating
    def test_video_attach_via_picker(self, galefling_data_dir, fetlife_credentials, sample_video):
        """The shipped picker path must leave the video form ready without submitting."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            ok, final_url = load_page(page, VIDEO_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)
            # Neutral for the same reason as the picture probe above.
            caption_text = mutating_post_tag()
            platform.prepare_post(caption_text, [sample_video])
            platform.suppress_native_file_dialog = True
            platform._do_prefill()
            state = wait_for_attachment(platform)
            wait_ms(1500)

            assert platform.picker_invocations == 1, (
                f'expected one chooseFiles() call, got {platform.picker_invocations}'
            )
            assert state.get('attached'), f'Video form never retained the file: {state}'
            assert 'video_video' in state.get('holders', []), (
                f'Video did not reach the named form field: {state}'
            )
            caption = _read_media_caption(page, is_video=True)
            assert caption.get('caption') == caption_text, f'Description did not stick: {caption}'
            assert caption.get('title') == caption_text, f'Video title did not stick: {caption}'
            consent = run_js(
                page,
                """
                (function() {
                    var box = document.querySelector(
                        'input[type="checkbox"][name="video[is_certified]"]'
                    );
                    return {present: !!box, checked: !!(box && box.checked)};
                })();
                """,
            )
            assert consent.get('checked'), f'Consent was not certified: {consent}'
            form = _upload_form_state(page, 'videos/new')
            assert form.get('stillOnComposer'), 'Must not navigate away without user submit'
        finally:
            close_webview(view, page, platform)

    @pytest.mark.non_mutating
    def test_video_composer_loads(self, galefling_data_dir, fetlife_credentials):
        """Verify the video composer loads with file input, submit button, and consent."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)

            ok, final_url = load_page(page, VIDEO_COMPOSER_URL, timeout_ms=20000)
            assert ok, f'Page load failed: {final_url}'
            assert '/login' not in final_url.lower(), f'Session expired: {final_url}'
            wait_ms(2000)

            result = _composer_elements(
                page, VIDEO_FILE_SELECTOR, FetLifePlatform.VIDEO_SUBMIT_LABEL
            )
            assert isinstance(result, dict), f'JS returned: {result}'
            assert result.get('fileInputFound'), 'File input not found'
            assert result.get('submitFound'), 'Upload button not found'
            assert result.get('attachControlVisible'), (
                f'Visible Choose File control not found: {result}'
            )
            assert 'video' in (result.get('fileInputAccept') or ''), (
                'File input does not accept video'
            )

            consent = call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent certification not set: {consent}'
            assert consent.get('names') == ['video[is_certified]'], (
                f'Unexpected certification fields: {consent}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.non_mutating
    def test_video_attach_via_platform(self, galefling_data_dir, fetlife_credentials, sample_video):
        """FetLifePlatform._attach_media() must load a file into the video form."""
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)

            ok, final_url = load_page(page, VIDEO_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)

            platform._image_path = sample_video
            assert platform.get_media_file_selector() == VIDEO_FILE_SELECTOR

            attach = call_platform(platform._attach_media, sample_video)
            assert attach.get('dispatched'), f'Attach failed: {attach}'

            state = wait_for_attachment(platform)
            assert state.get('attached'), f'Form never accepted the file: {state}'

            consent = call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent certification not set: {consent}'

            page_state = _upload_form_state(page, 'videos/new')
            assert page_state.get('stillOnComposer'), 'Must not navigate away without submit'
        finally:
            close_webview(view, page, platform)

    @pytest.mark.non_mutating
    def test_video_caption_capacity(self, galefling_data_dir, fetlife_credentials, sample_video):
        """`video[description]` must hold at least as much text as GaleFling will send.

        The picture-composer counterpart, with the same open-question framing — see
        ``test_picture_caption_capacity``. The video form is probed separately because
        nothing says the two fields share a limit, and ``video[title]`` is a third
        (``<input>``, not ``<textarea>``) whose own ceiling is reported here too.

        Never submits.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            ok, final_url = load_page(page, VIDEO_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)

            cap = platform.get_specs().max_text_length
            # Route _inject_media_caption() at video[description] rather than the
            # picture field, without attaching anything.
            platform._image_path = sample_video

            probe = _caption_capacity(page, platform, is_video=True, lengths=[cap, cap * 4])
            title = run_js(
                page,
                f"""
                (function() {{
                    var el = document.querySelector(
                        {json.dumps(FetLifePlatform.VIDEO_TITLE_SELECTOR)}
                    );
                    return el
                        ? {{maxlength: el.getAttribute('maxlength'), kept: el.value.length}}
                        : {{found: false}};
                }})();
                """,
            )
            print(f'\n  video description probe: {probe}\n  video[title]: {title}', flush=True)

            attrs = probe.get('attrs', {})
            assert attrs.get('found'), (
                f'{FetLifePlatform.VIDEO_CAPTION_SELECTOR} not on the composer: {attrs}'
            )

            at_cap = probe['observed'][0]
            assert at_cap['kept'] == cap, (
                f'video[description] holds only {at_cap["kept"]} of {cap} characters — '
                f'FetLife caps descriptions below FETLIFE_SPECS.max_text_length, so a '
                f'video post at the spec limit would be silently truncated: {probe}'
            )
        finally:
            close_webview(view, page, platform)

    @pytest.mark.mutating
    def test_video_upload_creates_a_post(
        self, galefling_data_dir, fetlife_credentials, sample_video
    ):
        """Upload a real video and prove it appears in the account's video gallery.

        The composer URL does not change on success — FetLife transfers and transcodes
        in place — so the gallery is the only honest post-condition. Cleanup is manual;
        the run prints the tag.

        **What this asserts is that media landed, not that it is a video.** The gallery
        renders an entry as its poster thumbnail, so a still image is what is actually
        checked — the same limit the Fansly video test documents, and for the same
        reason: there is no video-specific marker without playing it. The realistic
        failure (the transfer failing while the description posts) produces a gallery
        entry with no poster, and so does fail here.

        ``/videos/new`` posts to ``/videos/draft``, so what lands may be a draft rather
        than a published video; the gallery is the account's own, which lists both.
        """
        get_or_create_app()
        view, page, platform = create_webview(galefling_data_dir, ACCOUNT_ID)
        try:
            _ensure_session(page, fetlife_credentials)
            ok, final_url = load_page(page, VIDEO_COMPOSER_URL, timeout_ms=20000)
            assert ok and '/login' not in final_url.lower(), f'Session lost: {final_url}'
            wait_ms(2000)

            tag = mutating_post_text()

            print(f'\n  posting tag {tag} — delete this if the run fails')
            platform._image_path = sample_video

            attach = call_platform(platform._attach_media, sample_video)
            assert attach.get('dispatched'), f'Attach failed: {attach}'
            state = wait_for_attachment(platform)
            assert state.get('attached'), f'Form never accepted the file: {state}'

            call_platform(platform._inject_media_caption, tag)
            caption = _read_media_caption(page, is_video=True)
            assert tag in (caption.get('caption') or ''), (
                f'Description did not stick in the form: {caption}'
            )
            assert caption.get('title'), (
                f'video[title] is empty — FetLife rejects a titleless upload: {caption}'
            )

            consent = call_platform(platform._certify_upload_consent)
            assert consent.get('certified'), f'Consent not certified: {consent}'

            submit = _wait_for_enabled_submit(page, FetLifePlatform.VIDEO_SUBMIT_LABEL)
            assert submit.get('clicked'), f'Upload not clicked: {submit}'

            # The composer URL never changes: FetLife transfers and transcodes the
            # video asynchronously in place, so navigation cannot signal success.
            # Only the gallery proves the video landed.
            wait_ms(20000)
            posted = _wait_for_media_in_gallery(page, 'videos', tag)
            assert posted.get('found'), (
                f'Video {tag} never appeared in the gallery after upload: {posted}'
            )

            media = _published_media_report(page, tag)
            assert media.get('hasMedia'), (
                f'Gallery lists the description but renders no video or poster — the '
                f'transfer did not complete: {media}'
            )
            print(f'\n  FetLife video uploaded (tag {tag}) -> {posted.get("gallery")}')
            print(f'  media: {media}')
            print(
                f'  CLEANUP PENDING (leave up until any follow-up inspection is done) — delete the video tagged {tag}'
            )
        finally:
            close_webview(view, page, platform)
