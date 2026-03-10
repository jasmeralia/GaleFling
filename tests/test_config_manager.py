from src.core.config_manager import DEFAULT_CONFIG, ConfigManager


def test_config_manager_loads_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.config_manager.get_app_data_dir', lambda: tmp_path)
    manager = ConfigManager()
    assert manager.get('theme_mode') == DEFAULT_CONFIG['theme_mode']
    assert manager.snapchat_landscape_mode == 'crop'
    assert manager.snapchat_multi_image_mode == 'first'
    assert manager.preview_worker_count == 2
    assert manager.window_geometry == DEFAULT_CONFIG['window_geometry']


def test_config_manager_persists_changes(tmp_path, monkeypatch):
    monkeypatch.setattr('src.core.config_manager.get_app_data_dir', lambda: tmp_path)
    manager = ConfigManager()
    manager.set('theme_mode', 'dark')
    manager.snapchat_landscape_mode = 'rotate'
    manager.snapchat_multi_image_mode = 'slideshow'
    manager.preview_worker_count = 3

    path = tmp_path / 'app_config.json'
    assert path.exists()

    manager2 = ConfigManager()
    assert manager2.theme_mode == 'dark'
    assert manager2.snapchat_landscape_mode == 'rotate'
    assert manager2.snapchat_multi_image_mode == 'slideshow'
    assert manager2.preview_worker_count == 3
