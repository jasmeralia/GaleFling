"""Tests for log uploader."""

from __future__ import annotations

import base64
import os
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
    assert payload['wer_reports'] == []
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


def test_upload_upgrade_required_returns_upgrade_message(tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    config.set('log_upload_enabled', True)

    monkeypatch.setattr(log_uploader, 'get_logs_dir', lambda: tmp_path / 'logs')
    monkeypatch.setattr(log_uploader, 'get_current_log_path', lambda: None)
    monkeypatch.setattr(log_uploader, 'get_ffmpeg_version', lambda: '7.1.1-custom')

    def fake_post(url, json, headers, timeout):
        return SimpleNamespace(
            status_code=426,
            json=lambda: {
                'error_code': 'LOG-CLIENT-TOO-OLD',
                'message': 'App version too old for log submission.',
                'min_supported_version': '1.5.1',
            },
            text='upgrade required',
        )

    monkeypatch.setattr(log_uploader.requests, 'post', fake_post)

    uploader = LogUploader(config)
    success, message, details = uploader.upload('notes')

    assert not success
    assert 'upgrade' in message.lower()
    assert 'retest' in message.lower()
    assert '1.5.1' in message
    assert 'LOG-CLIENT-TOO-OLD' in details


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


def test_upload_success_includes_wer_reports(tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    config.set('log_upload_enabled', True)

    logs_dir = tmp_path / 'logs'
    logs_dir.mkdir(parents=True)
    (logs_dir / 'screenshots').mkdir(parents=True)
    current_log = logs_dir / 'app_current.log'
    current_log.write_text('current log')

    monkeypatch.setattr(log_uploader, 'get_logs_dir', lambda: logs_dir)
    monkeypatch.setattr(log_uploader, 'get_current_log_path', lambda: current_log)
    monkeypatch.setattr(log_uploader, 'get_installation_id', lambda: 'install-123')
    monkeypatch.setattr(log_uploader, 'get_os_info', lambda: {'platform': 'TestOS', 'version': '1'})
    monkeypatch.setattr(log_uploader, 'get_ffmpeg_version', lambda: '7.1.1-custom')
    monkeypatch.setattr(
        LogUploader,
        '_collect_wer_reports',
        lambda _self: [{'filename': 'wer_report.wer', 'content': 'dGVzdA=='}],
    )

    captured = {}

    def fake_post(url, json, headers, timeout):
        captured['payload'] = json
        return SimpleNamespace(status_code=200, json=lambda: {'upload_id': 'abc123'}, text='')

    monkeypatch.setattr(log_uploader.requests, 'post', fake_post)

    uploader = LogUploader(config)
    success, message, details = uploader.upload('User notes')

    assert success
    assert 'abc123' in message
    assert details == ''
    assert captured['payload']['wer_reports'] == [
        {'filename': 'wer_report.wer', 'content': 'dGVzdA=='}
    ]


def test_collect_wer_reports_reads_local_and_programdata_paths(tmp_path, monkeypatch):
    config = _make_config(tmp_path, monkeypatch)
    uploader = LogUploader(config)

    local_appdata = tmp_path / 'LocalAppData'
    program_data = tmp_path / 'ProgramData'
    local_report = (
        local_appdata
        / 'Microsoft'
        / 'Windows'
        / 'WER'
        / 'ReportArchive'
        / 'AppCrash_GaleFling.exe_001'
        / 'Report.wer'
    )
    program_report = (
        program_data
        / 'Microsoft'
        / 'Windows'
        / 'WER'
        / 'ReportQueue'
        / 'AppHang_GaleFling.exe_001'
        / 'Report.wer'
    )
    local_report.parent.mkdir(parents=True, exist_ok=True)
    program_report.parent.mkdir(parents=True, exist_ok=True)
    local_report.write_text('local report', encoding='utf-8')
    program_report.write_text('program report', encoding='utf-8')

    os.utime(local_report, (1000, 1000))
    os.utime(program_report, (2000, 2000))

    monkeypatch.setattr(log_uploader.sys, 'platform', 'win32')
    monkeypatch.setenv('LOCALAPPDATA', str(local_appdata))
    monkeypatch.setenv('PROGRAMDATA', str(program_data))

    reports = uploader._collect_wer_reports()
    filenames = [entry['filename'] for entry in reports]
    decoded = [
        base64.b64decode(entry['content'].encode('ascii')).decode('utf-8') for entry in reports
    ]

    assert filenames[0].startswith('AppHang_GaleFling.exe_001_')
    assert filenames[1].startswith('AppCrash_GaleFling.exe_001_')
    assert decoded == ['program report', 'local report']
