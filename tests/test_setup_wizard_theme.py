from src.gui.setup_wizard import SetupWizard


class DummyAuthManager:
    def get_twitter_auth(self):
        return None

    def get_bluesky_auth(self):
        return None

    def get_bluesky_auth_alt(self):
        return None


def test_setup_wizard_applies_style(qtbot):
    wizard = SetupWizard(DummyAuthManager(), theme_mode='dark')
    qtbot.addWidget(wizard)
    wizard.show()
    qtbot.waitExposed(wizard)

    assert 'background-color' in wizard.styleSheet()
