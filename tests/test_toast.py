from PyQt6.QtWidgets import QMainWindow

from src.gui.toast import Toast, show_toast


def test_show_toast_creates_visible_confirmation(qtbot):
    window = QMainWindow()
    window.resize(700, 500)
    qtbot.addWidget(window)
    window.show()

    toast = show_toast(window, 'Post scheduled')

    assert isinstance(toast, Toast)
    assert toast.text() == 'Post scheduled'
    assert toast.isVisible()
    assert toast.x() == (window.width() - toast.width()) // 2
