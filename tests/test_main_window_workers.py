from __future__ import annotations

from pathlib import Path

import requests

from src.gui.main_window import PostWorker, UpdateDownloadWorker


class _DummyPlatform:
    def __init__(self):
        self.calls: list[tuple[str, list[Path] | None]] = []

    def post(self, text: str, media_paths):
        self.calls.append((text, media_paths))
        return f'posted:{len(self.calls)}'


class _DummyResponse:
    def __init__(self, payload: bytes, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {'Content-Length': str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'HTTP {self.status_code}')

    def iter_content(self, chunk_size: int = 1024 * 256):
        for idx in range(0, len(self._payload), chunk_size):
            yield self._payload[idx : idx + chunk_size]


class _ChunkedDummyResponse(_DummyResponse):
    def __init__(self, chunks: list[bytes], status_code: int = 200):
        super().__init__(b''.join(chunks), status_code=status_code)
        self._chunks = chunks

    def iter_content(self, chunk_size: int = 1024 * 256):
        return iter(self._chunks)


def test_post_worker_filters_missing_paths_and_emits_results(tmp_path):
    existing = tmp_path / 'exists.jpg'
    existing.write_bytes(b'x')
    missing = tmp_path / 'missing.jpg'

    twitter = _DummyPlatform()
    snapchat = _DummyPlatform()

    worker = PostWorker(
        platforms={'twitter_1': twitter, 'snapchat_1': snapchat},
        text='hello world',
        processed_media={
            'twitter': [existing, missing, None],
            'snapchat': [missing, None],
        },
        platform_groups={
            'twitter_1': 'twitter',
            'snapchat_1': 'snapchat',
        },
    )

    emitted: list[list[str]] = []
    worker.finished.connect(lambda results: emitted.append(results))

    worker.run()

    assert twitter.calls == [('hello world', [existing])]
    assert snapchat.calls == [('hello world', None)]
    assert emitted == [['posted:1', 'posted:1']]


def test_update_download_worker_success_writes_installer(monkeypatch, tmp_path):
    payload = b'MZ' + (b'A' * (5 * 1024 * 1024))
    target = tmp_path / 'GaleFlingSetup.exe'

    monkeypatch.setattr(
        'src.gui.main_window.requests.get',
        lambda *_a, **_k: _DummyResponse(payload),
    )

    worker = UpdateDownloadWorker(
        'https://example.invalid/setup.exe', target, expected_size=len(payload)
    )

    progress_values: list[int] = []
    finished_values: list[tuple[bool, Path | None, str]] = []
    worker.progress.connect(progress_values.append)
    worker.finished.connect(lambda ok, path, error: finished_values.append((ok, path, error)))

    worker.run()

    assert target.exists()
    assert target.read_bytes()[:2] == b'MZ'
    assert any(value > 0 for value in progress_values)
    assert finished_values == [(True, target, '')]
    assert not target.with_suffix('.exe.part').exists()


def test_update_download_worker_invalid_binary_returns_error(monkeypatch, tmp_path):
    payload = b'ZZ' + (b'A' * (5 * 1024 * 1024))
    target = tmp_path / 'GaleFlingSetup.exe'

    monkeypatch.setattr(
        'src.gui.main_window.requests.get',
        lambda *_a, **_k: _DummyResponse(payload),
    )

    worker = UpdateDownloadWorker('https://example.invalid/setup.exe', target)

    finished_values: list[tuple[bool, Path | None, str]] = []
    worker.finished.connect(lambda ok, path, error: finished_values.append((ok, path, error)))

    worker.run()

    assert not target.exists()
    assert not target.with_suffix('.exe.part').exists()
    assert len(finished_values) == 1
    assert finished_values[0][0] is False
    assert finished_values[0][1] is None
    assert 'valid Windows executable' in finished_values[0][2]


def test_update_download_worker_size_mismatch_returns_error(monkeypatch, tmp_path):
    payload = b'MZ' + (b'A' * (5 * 1024 * 1024))
    target = tmp_path / 'GaleFlingSetup.exe'

    monkeypatch.setattr(
        'src.gui.main_window.requests.get',
        lambda *_a, **_k: _DummyResponse(payload),
    )

    worker = UpdateDownloadWorker(
        'https://example.invalid/setup.exe',
        target,
        expected_size=len(payload) + 10,
    )
    finished_values: list[tuple[bool, Path | None, str]] = []
    worker.finished.connect(lambda ok, path, error: finished_values.append((ok, path, error)))

    worker.run()

    assert not target.exists()
    assert len(finished_values) == 1
    assert finished_values[0][0] is False
    assert 'size mismatch' in finished_values[0][2]


def test_update_download_worker_rejects_too_small_installer(monkeypatch, tmp_path):
    payload = b'MZ' + (b'A' * 1024)
    target = tmp_path / 'GaleFlingSetup.exe'

    monkeypatch.setattr(
        'src.gui.main_window.requests.get',
        lambda *_a, **_k: _DummyResponse(payload),
    )

    worker = UpdateDownloadWorker('https://example.invalid/setup.exe', target)
    finished_values: list[tuple[bool, Path | None, str]] = []
    worker.finished.connect(lambda ok, path, error: finished_values.append((ok, path, error)))

    worker.run()

    assert not target.exists()
    assert len(finished_values) == 1
    assert finished_values[0][0] is False
    assert 'too small' in finished_values[0][2]


def test_update_download_worker_ignores_empty_chunks(monkeypatch, tmp_path):
    payload = b'MZ' + (b'B' * (5 * 1024 * 1024))
    target = tmp_path / 'GaleFlingSetup.exe'
    chunks = [b'', payload[:100], b'', payload[100:]]

    monkeypatch.setattr(
        'src.gui.main_window.requests.get',
        lambda *_a, **_k: _ChunkedDummyResponse(chunks),
    )

    worker = UpdateDownloadWorker('https://example.invalid/setup.exe', target)
    finished_values: list[tuple[bool, Path | None, str]] = []
    worker.finished.connect(lambda ok, path, error: finished_values.append((ok, path, error)))

    worker.run()

    assert target.exists()
    assert finished_values == [(True, target, '')]
