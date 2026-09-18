import json

from src.core.config_manager import DEFAULT_CONFIG, ConfigManager


def test_config_manager_loads_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.config_manager.get_app_data_dir', lambda: tmp_path)
    manager = ConfigManager()
    assert manager.snapchat_landscape_mode == 'crop'
    assert manager.snapchat_multi_image_mode == 'first'
    assert manager.preview_worker_count == 2
    assert manager.window_geometry == DEFAULT_CONFIG['window_geometry']


def test_config_manager_persists_changes(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.config_manager.get_app_data_dir', lambda: tmp_path)
    manager = ConfigManager()
    manager.snapchat_landscape_mode = 'rotate'
    manager.snapchat_multi_image_mode = 'slideshow'
    manager.preview_worker_count = 3

    path = tmp_path / 'app_config.json'
    assert path.exists()

    manager2 = ConfigManager()
    assert manager2.snapchat_landscape_mode == 'rotate'
    assert manager2.snapchat_multi_image_mode == 'slideshow'
    assert manager2.preview_worker_count == 3


def test_config_manager_reset_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.config_manager.get_app_data_dir', lambda: tmp_path)
    manager = ConfigManager()
    manager.snapchat_landscape_mode = 'rotate'
    manager.preview_worker_count = 4

    manager.reset_to_defaults()

    assert manager.snapchat_landscape_mode == DEFAULT_CONFIG['snapchat_landscape_mode']
    assert manager.preview_worker_count == DEFAULT_CONFIG['preview_worker_count']

    # Verify persisted to disk
    saved = json.loads((tmp_path / 'app_config.json').read_text())
    assert saved['preview_worker_count'] == DEFAULT_CONFIG['preview_worker_count']


def test_recent_emoji_default_get_set_and_cap(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.config_manager.get_app_data_dir', lambda: tmp_path)
    manager = ConfigManager()

    assert manager.recent_emoji == []

    recent = [f'emoji-{index}' for index in range(30)]
    manager.recent_emoji = recent

    assert manager.recent_emoji == recent[:24]
    saved = json.loads((tmp_path / 'app_config.json').read_text())
    assert saved['recent_emoji'] == recent[:24]

    manager._config['recent_emoji'] = 'not-a-list'
    assert manager.recent_emoji == []


def test_notification_email_default_get_set_and_strips_whitespace(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.config_manager.get_app_data_dir', lambda: tmp_path)
    manager = ConfigManager()

    assert manager.notification_email == ''

    manager.notification_email = '  rin@example.com  '
    assert manager.notification_email == 'rin@example.com'

    saved = json.loads((tmp_path / 'app_config.json').read_text())
    assert saved['notification_email'] == 'rin@example.com'


def test_notify_on_scheduled_success_default_get_set(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.config_manager.get_app_data_dir', lambda: tmp_path)
    manager = ConfigManager()

    assert manager.notify_on_scheduled_success is False

    manager.notify_on_scheduled_success = True
    assert manager.notify_on_scheduled_success is True

    saved = json.loads((tmp_path / 'app_config.json').read_text())
    assert saved['notify_on_scheduled_success'] is True


def test_autostart_defaults_and_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.config_manager.get_app_data_dir', lambda: tmp_path)
    manager = ConfigManager()

    assert manager.autostart_enabled is True
    assert manager.autostart_launch_mode == 'tray'

    manager.autostart_enabled = False
    manager.autostart_launch_mode = 'window'

    restored = ConfigManager()
    assert restored.autostart_enabled is False
    assert restored.autostart_launch_mode == 'window'


def test_fresh_install_detected_only_before_first_save(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.config_manager.get_app_data_dir', lambda: tmp_path)
    manager = ConfigManager()

    assert manager.is_fresh_install is True
    assert manager.autostart_enabled is True

    manager.snapchat_landscape_mode = 'rotate'  # any set() call persists to disk

    reloaded = ConfigManager()
    assert reloaded.is_fresh_install is False
