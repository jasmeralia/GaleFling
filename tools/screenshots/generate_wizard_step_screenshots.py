#!/usr/bin/env python3
"""Generate one screenshot per setup wizard step, for visual review.

Runs GaleFling's real SetupWizard against a throwaway AuthManager pointed at
an isolated temp HOME (offscreen-rendered, no real credentials), and grabs a
PNG of every page in wizard order -- this is a review tool, not part of the
README screenshot set in docs/images/.

Usage:
    .venv/bin/python tools/screenshots/generate_wizard_step_screenshots.py [out_dir]

Defaults to writing into a fresh temp directory (printed on completion) if
out_dir is omitted.
"""

# The HOME/QT_QPA_PLATFORM env vars below must be set before importing
# anything that touches app config paths or Qt.
# ruff: noqa: E402

import os
import re
import sys
import tempfile
from pathlib import Path

_SCRATCH_HOME = tempfile.mkdtemp(prefix='galefling-screenshot-home-')
os.environ['HOME'] = _SCRATCH_HOME
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PIL import Image
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication

from src.core.auth_manager import AuthManager
from src.gui.setup_wizard import SetupWizard
from src.utils.theme import apply_theme


def _qpixmap_to_pil(pixmap) -> Image.Image:
    qimage = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = qimage.width(), qimage.height()
    buf = qimage.bits().asstring(qimage.sizeInBytes())
    return Image.frombuffer('RGBA', (width, height), buf, 'raw', 'RGBA', 0, 1).copy()


def _slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def main() -> None:
    out_dir = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(tempfile.mkdtemp(prefix='galefling-wizard-steps-'))
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    apply_theme(app)

    auth_manager = AuthManager()  # fresh, first-run state
    wizard = SetupWizard(auth_manager)
    apply_theme(app, wizard)
    wizard.resize(640, 780)
    wizard.show()
    QApplication.processEvents()

    steps = wizard._step_rail._steps  # [(label, page_id), ...] in wizard order
    for index, (label, page_id) in enumerate(steps, start=1):
        wizard.setCurrentId(page_id)
        page = wizard.currentPage()
        if page is not None:
            page.adjustSize()
        wizard.adjustSize()
        wizard.resize(640, 780)
        for _ in range(5):
            QApplication.processEvents()

        pixmap = wizard.grab()
        image = _qpixmap_to_pil(pixmap).convert('RGB')
        name = f'{index:02d}-{_slug(label)}.png'
        path = out_dir / name
        image.save(path)
        print(f'Wrote {path} ({image.width}x{image.height})')

    wizard.close()
    print(f'\n{len(steps)} step screenshots written to {out_dir}')


if __name__ == '__main__':
    main()
