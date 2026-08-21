from PyQt6.QtWidgets import QWizard

from src.gui.setup_wizard import SetupWizard


class DummyAuthManager:
    def get_twitter_app_credentials(self):
        return None

    def get_twitter_auth(self):
        return None

    def get_bluesky_auth(self):
        return None

    def get_bluesky_auth_alt(self):
        return None

    def get_account_credentials(self, account_id):
        return None

    def get_account(self, account_id):
        return None

    def get_meta_threads_app_credentials(self):
        return None

    def get_meta_instagram_app_credentials(self):
        return None

    def get_meta_facebook_app_credentials(self):
        return None


class DummyConfigManager:
    def __init__(self):
        self.notification_email = ''


def test_setup_wizard_applies_style(qtbot):
    wizard = SetupWizard(DummyAuthManager(), DummyConfigManager())
    qtbot.addWidget(wizard)
    wizard.show()
    qtbot.waitExposed(wizard)

    assert wizard.wizardStyle() == QWizard.WizardStyle.ModernStyle
