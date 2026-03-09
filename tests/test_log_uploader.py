"""Tests for log uploader."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import requests

import src.core.log_uploader as log_uploader
from src.core.config_manager import ConfigManager
from src.core.log_uploader import LogUploader


def _make_config(tmp_path, monkeypatch) -> ConfigManager:
    import src.core.config_manager as config_manager

    monkeypatch.setattr(config_manager, 'get_app_data_dir', lambda: tmp_path)
    return ConfigManager()


def test_upload_disabled_returns_error(tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    config.set('log_upload_enabled', False)

    uploader = LogUploader(config)
    success, message, details = uploader.upload('Some notes')

    assert not success
    assert 'disabled' in message.lower()
    assert 'LOG-DISABLED' in details


def test_upload_requires_notes(tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    config.set('log_upload_enabled', True)

    uploader = LogUploader(config)
    success, message, details = uploader.upload('   ')

    assert not success
    assert 'describe' in message.lower()
    assert 'LOG-NOTES-MISSING' in details


def test_upload_success_includes_logs_and_screenshots(tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    config.set('log_upload_enabled', True)

    logs_dir = tmp_path / 'logs'
    logs_dir.mkdir(parents=True)
    (logs_dir / 'screenshots').mkdir(parents=True)

    current_log = logs_dir / 'app_current.log'
    current_log.write_text('current log')
    other_log = logs_dir / 'app_older.log'
    other_log.write_text('older log')
    crash_log = logs_dir / 'crash_20260219_123456.log'
    crash_log.write_text('crash log')
    fatal_log = logs_dir / 'fatal_errors.log'
    fatal_log.write_text('fatal log')

    screenshot = logs_dir / 'screenshots' / 'error_20240101.png'
    screenshot.write_bytes(b'pngdata')

    monkeypatch.setattr(log_uploader, 'get_logs_dir', lambda: logs_dir)
    monkeypatch.setattr(log_uploader, 'get_current_log_path', lambda: current_log)
    monkeypatch.setattr(log_uploader, 'get_installation_id', lambda: 'install-123')
    monkeypatch.setattr(log_uploader, 'get_os_info', lambda: {'platform': 'TestOS', 'version': '1'})
    monkeypatch.setattr(log_uploader, 'get_ffmpeg_version', lambda: '7.1.1-custom')

    captured = {}

    def fake_post(url, json, headers, timeout):
        captured['url'] = url
        captured['payload'] = json
        return SimpleNamespace(status_code=200, json=lambda: {'upload_id': 'abc123'}, text='')

    monkeypatch.setattr(log_uploader.requests, 'post', fake_post)

    uploader = LogUploader(config)
    success, message, details = uploader.upload('User notes')

    assert success
    assert 'abc123' in message
    assert details == ''

    payload = captured['payload']
    assert payload['user_id'] == 'install-123'
    assert payload['ffmpeg_version'] == '7.1.1-custom'
    assert len(payload['log_files']) >= 2
    assert len(payload['screenshots']) == 1
    assert payload['screenshots'][0]['filename'] == screenshot.name
    filenames = {entry['filename'] for entry in payload['log_files']}
    assert 'fatal_errors.log' in filenames
    assert crash_log.name in filenames

    encoded = payload['log_files'][0]['content']
    assert base64.b64decode(encoded.encode('ascii'))


def test_upload_http_error_returns_details(tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    config.set('log_upload_enabled', True)

    monkeypatch.setattr(log_uploader, 'get_logs_dir', lambda: tmp_path / 'logs')
    monkeypatch.setattr(log_uploader, 'get_current_log_path', lambda: None)

    def fake_post(url, json, headers, timeout):
        return SimpleNamespace(status_code=500, json=lambda: {}, text='server down')

    monkeypatch.setattr(log_uploader.requests, 'post', fake_post)

    uploader = LogUploader(config)
    success, message, details = uploader.upload('notes')

    assert not success
    assert 'HTTP 500' in message
    assert 'LOG-HTTP-500' in details
    assert 'server down' in details


def test_upload_timeout_returns_error(tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    config.set('log_upload_enabled', True)

    monkeypatch.setattr(log_uploader, 'get_logs_dir', lambda: tmp_path / 'logs')
    monkeypatch.setattr(log_uploader, 'get_current_log_path', lambda: None)

    def fake_post(url, json, headers, timeout):
        raise requests.Timeout('timeout')

    monkeypatch.setattr(log_uploader.requests, 'post', fake_post)

    uploader = LogUploader(config)
    success, message, details = uploader.upload('notes')

    assert not success
    assert 'timed out' in message.lower()
    assert 'LOG-TIMEOUT' in details


def test_upload_connection_error_returns_error(tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    config.set('log_upload_enabled', True)

    monkeypatch.setattr(log_uploader, 'get_logs_dir', lambda: tmp_path / 'logs')
    monkeypatch.setattr(log_uploader, 'get_current_log_path', lambda: None)

    def fake_post(url, json, headers, timeout):
        raise requests.ConnectionError('no route')

    monkeypatch.setattr(log_uploader.requests, 'post', fake_post)

    uploader = LogUploader(config)
    success, message, details = uploader.upload('notes')

    assert not success
    assert 'connect' in message.lower()
    assert 'LOG-CONNECTION' in details


def test_upload_unexpected_exception_returns_error(tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    config.set('log_upload_enabled', True)

    monkeypatch.setattr(log_uploader, 'get_logs_dir', lambda: tmp_path / 'logs')
    monkeypatch.setattr(log_uploader, 'get_current_log_path', lambda: None)

    def fake_post(url, json, headers, timeout):
        raise RuntimeError('boom')

    monkeypatch.setattr(log_uploader.requests, 'post', fake_post)

    uploader = LogUploader(config)
    success, message, details = uploader.upload('notes')

    assert not success
    assert 'unexpected' in message.lower()
    assert 'LOG-EXCEPTION' in details
