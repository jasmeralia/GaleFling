"""GaleFling - Application entry point."""

import os
import sys

# Ensure src is importable when running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from src.core.auth_manager import AuthManager
from src.core.config_manager import ConfigManager
from src.core.logger import setup_logging
from src.gui.main_window import MainWindow
from src.utils.constants import APP_NAME
from src.utils.theme import apply_theme


def main():
    # Initialize config first
    config = ConfigManager()

    # Set up logging
    setup_logging(debug_mode=config.debug_mode)

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_theme(app, None, config.theme_mode)

    # Enable high DPI support
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)

    # Initialize auth
    auth_manager = AuthManager()

    # Create and show main window
    window = MainWindow(config, auth_manager)
    window.show()
    apply_theme(app, window, config.theme_mode)

    # Post-show actions
    window.restore_draft()
    window.check_for_updates_on_startup()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
