"""Design tokens for GaleFling's dark interface."""

# Color tokens (dark palette)
CANVAS = '#0A0D13'
SURFACE = '#12161F'
SURFACE_RAISED = '#1B212D'
SURFACE_INSET = '#0D1119'
BORDER = '#262D3B'
ACCENT = '#5B84C4'
SUCCESS = '#5C7CFA'
WARNING = '#F5A623'
DANGER = '#F87171'
TEXT = '#FFFFFF'
# For genuinely inactive/disabled content only. For secondary text that
# still needs to be read at a glance (handles, counter labels, captions),
# use TEXT_SECONDARY instead — TEXT_MUTED is too dim at the small point
# sizes those labels use.
TEXT_MUTED = '#8E96AA'
TEXT_SECONDARY = '#C9D0E3'

# Qt point sizes map the deck's CSS-pixel scale to typical desktop DPI.
# Qt's QSS `font-weight` only accepts normal/bold or 100-900 in steps of 100
# (https://doc.qt.io/qt-6/stylesheet-reference.html#font-weight) — any other
# value makes Qt silently drop the *entire* declaration block it appears in,
# including unrelated properties like color. Keep these on that scale.
FONT_HEADING = (18, 700)
FONT_BODY_STRONG = (10, 600)
FONT_BODY = (10, 400)
FONT_MONO = (9, 400)


def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of a '#rrggbb' color."""
    hex_color = hex_color.lstrip('#')
    channels = (int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def linearize(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linearize(c) for c in channels)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG contrast ratio between two '#rrggbb' colors."""
    l_a, l_b = _relative_luminance(hex_a), _relative_luminance(hex_b)
    lighter, darker = max(l_a, l_b), min(l_a, l_b)
    return (lighter + 0.05) / (darker + 0.05)


def legible_accent(hex_color: str, background: str = SURFACE, minimum: float = 3.0) -> str:
    """A brand/accent color for use as text, or TEXT if it can't be read on `background`.

    Some platform brand colors (e.g. Threads' black) have no usable contrast
    against the dark theme's near-black surfaces. Use this wherever a brand
    color is applied as foreground text so it stays legible.
    """
    return hex_color if contrast_ratio(hex_color, background) >= minimum else TEXT


def darken(hex_color: str, factor: float) -> str:
    """Scale `hex_color` toward black by `factor` (e.g. 0.85 = 15% darker)."""
    hex_color = hex_color.lstrip('#')
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r, g, b = (max(0, min(255, round(c * factor))) for c in (r, g, b))
    return f'#{r:02X}{g:02X}{b:02X}'


def with_alpha(hex_color: str, alpha: float) -> str:
    """Return `hex_color` as a QSS `rgba(...)` string with the given opacity (0-1)."""
    hex_color = hex_color.lstrip('#')
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f'rgba({r}, {g}, {b}, {alpha})'
