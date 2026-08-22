"""Persistent local queue for scheduled posts."""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.utils.helpers import get_app_data_dir

SCHEDULED_STATES = {'pending', 'in_flight', 'posted', 'failed'}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(UTC)


@dataclass(frozen=True)
class ScheduledPost:
    id: str
    text: str
    account_ids: tuple[str, ...]
    media_paths: tuple[Path, ...]
    processed_media: dict[str, tuple[Path, ...]]
    due_at: datetime
    created_at: datetime
    updated_at: datetime
    state: str = 'pending'
    results: tuple[dict, ...] = ()

    @property
    def is_missed(self) -> bool:
        return self.state == 'pending' and self.due_at <= _utc_now()


class ScheduledPostQueue:
    """SQLite-backed scheduled-post store with owned media copies."""

    def __init__(self, database_path: Path | None = None) -> None:
        app_dir = get_app_data_dir()
        self._database_path = database_path or app_dir / 'scheduled_posts.sqlite3'
        self._media_dir = self._database_path.parent / 'scheduled_media'
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._media_dir.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute('PRAGMA journal_mode = WAL')
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_posts (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    account_ids TEXT NOT NULL,
                    media_paths TEXT NOT NULL,
                    processed_media TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN ('pending', 'in_flight', 'posted', 'failed')
                    ),
                    results TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            connection.execute(
                'CREATE INDEX IF NOT EXISTS scheduled_posts_due_idx '
                'ON scheduled_posts (state, due_at)'
            )

    def add(
        self,
        *,
        text: str,
        account_ids: list[str],
        media_paths: list[Path],
        processed_media: dict[str, list[Path | None]],
        due_at: datetime,
    ) -> ScheduledPost:
        post_id = str(uuid.uuid4())
        owned_media, owned_processed = self._copy_media(post_id, media_paths, processed_media)
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO scheduled_posts (
                    id, text, account_ids, media_paths, processed_media,
                    due_at, created_at, updated_at, state, results
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', '[]')
                """,
                (
                    post_id,
                    text,
                    json.dumps(account_ids),
                    json.dumps([str(path) for path in owned_media]),
                    json.dumps(
                        {
                            group: [str(path) for path in paths]
                            for group, paths in owned_processed.items()
                        }
                    ),
                    _as_utc(due_at).isoformat(),
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
        post = self.get(post_id)
        if post is None:
            raise RuntimeError('Scheduled post disappeared immediately after insertion')
        return post

    def update(
        self,
        post_id: str,
        *,
        text: str,
        account_ids: list[str],
        media_paths: list[Path],
        processed_media: dict[str, list[Path | None]],
        due_at: datetime,
    ) -> ScheduledPost:
        if self.get(post_id) is None:
            raise KeyError(post_id)
        owned_media, owned_processed = self._replace_media(post_id, media_paths, processed_media)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE scheduled_posts
                SET text = ?, account_ids = ?, media_paths = ?, processed_media = ?,
                    due_at = ?, updated_at = ?, state = 'pending', results = '[]'
                WHERE id = ?
                """,
                (
                    text,
                    json.dumps(account_ids),
                    json.dumps([str(path) for path in owned_media]),
                    json.dumps(
                        {
                            group: [str(path) for path in paths]
                            for group, paths in owned_processed.items()
                        }
                    ),
                    _as_utc(due_at).isoformat(),
                    _utc_now().isoformat(),
                    post_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(post_id)
        post = self.get(post_id)
        if post is None:
            raise KeyError(post_id)
        return post

    def get(self, post_id: str) -> ScheduledPost | None:
        with self._connect() as connection:
            row = connection.execute(
                'SELECT * FROM scheduled_posts WHERE id = ?', (post_id,)
            ).fetchone()
        return self._from_row(row) if row else None

    def list_pending(self) -> list[ScheduledPost]:
        return self._select("SELECT * FROM scheduled_posts WHERE state = 'pending' ORDER BY due_at")

    def list_missed(self, now: datetime | None = None) -> list[ScheduledPost]:
        cutoff = _as_utc(now or _utc_now()).isoformat()
        return self._select(
            "SELECT * FROM scheduled_posts WHERE state = 'pending' AND due_at <= ? ORDER BY due_at",
            (cutoff,),
        )

    def claim_due(
        self,
        now: datetime | None = None,
        *,
        exclude_ids: set[str] | None = None,
    ) -> ScheduledPost | None:
        cutoff = _as_utc(now or _utc_now()).isoformat()
        excluded = sorted(exclude_ids or set())
        exclusion_sql = ''
        params: list[str] = [cutoff]
        if excluded:
            placeholders = ', '.join('?' for _ in excluded)
            exclusion_sql = f' AND id NOT IN ({placeholders})'
            params.extend(excluded)
        with self._connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute(
                "SELECT * FROM scheduled_posts WHERE state = 'pending' AND due_at <= ?"
                + exclusion_sql
                + ' ORDER BY due_at LIMIT 1',
                tuple(params),
            ).fetchone()
            if row is None:
                return None
            cursor = connection.execute(
                "UPDATE scheduled_posts SET state = 'in_flight', updated_at = ? "
                "WHERE id = ? AND state = 'pending'",
                (_utc_now().isoformat(), row['id']),
            )
            if cursor.rowcount != 1:
                return None
        return self.get(str(row['id']))

    def reset_in_flight(self) -> int:
        """Recover items interrupted by an app or machine shutdown."""
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE scheduled_posts SET state = 'pending', updated_at = ? "
                "WHERE state = 'in_flight'",
                (_utc_now().isoformat(),),
            )
        return cursor.rowcount

    def mark_results(self, post_id: str, results: list[dict]) -> ScheduledPost:
        state = (
            'posted'
            if results and all(bool(result.get('success')) for result in results)
            else 'failed'
        )
        with self._connect() as connection:
            cursor = connection.execute(
                'UPDATE scheduled_posts SET state = ?, results = ?, updated_at = ? WHERE id = ?',
                (state, json.dumps(results, default=str), _utc_now().isoformat(), post_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(post_id)
        post = self.get(post_id)
        if post is None:
            raise KeyError(post_id)
        return post

    def delete(self, post_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute('DELETE FROM scheduled_posts WHERE id = ?', (post_id,))
        if cursor.rowcount:
            shutil.rmtree(self._media_dir / post_id, ignore_errors=True)
        return bool(cursor.rowcount)

    def _select(self, query: str, params: tuple[str, ...] = ()) -> list[ScheduledPost]:
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def _copy_media(
        self,
        post_id: str,
        media_paths: list[Path],
        processed_media: dict[str, list[Path | None]],
    ) -> tuple[list[Path], dict[str, list[Path]]]:
        post_dir = self._media_dir / post_id
        originals_dir = post_dir / 'originals'
        originals_dir.mkdir(parents=True, exist_ok=True)
        owned_media = [
            self._copy_one(path, originals_dir, index) for index, path in enumerate(media_paths)
        ]
        owned_processed: dict[str, list[Path]] = {}
        for group, paths in processed_media.items():
            group_dir = post_dir / 'processed' / group
            valid_paths = [path for path in paths if path is not None and path.exists()]
            if not valid_paths:
                continue
            group_dir.mkdir(parents=True, exist_ok=True)
            owned_processed[group] = [
                self._copy_one(path, group_dir, index) for index, path in enumerate(valid_paths)
            ]
        return owned_media, owned_processed

    def _replace_media(
        self,
        post_id: str,
        media_paths: list[Path],
        processed_media: dict[str, list[Path | None]],
    ) -> tuple[list[Path], dict[str, list[Path]]]:
        staging_id = f'.{post_id}-{uuid.uuid4().hex}.staging'
        staged_media, staged_processed = self._copy_media(staging_id, media_paths, processed_media)
        staging_dir = self._media_dir / staging_id
        final_dir = self._media_dir / post_id
        shutil.rmtree(final_dir, ignore_errors=True)
        staging_dir.rename(final_dir)

        def final_path(path: Path) -> Path:
            return final_dir / path.relative_to(staging_dir)

        return (
            [final_path(path) for path in staged_media],
            {
                group: [final_path(path) for path in paths]
                for group, paths in staged_processed.items()
            },
        )

    @staticmethod
    def _copy_one(source: Path, directory: Path, index: int) -> Path:
        destination = directory / f'{index:02d}{source.suffix.lower()}'
        shutil.copy2(source, destination)
        return destination

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ScheduledPost:
        processed = json.loads(row['processed_media'])
        return ScheduledPost(
            id=str(row['id']),
            text=str(row['text']),
            account_ids=tuple(json.loads(row['account_ids'])),
            media_paths=tuple(Path(path) for path in json.loads(row['media_paths'])),
            processed_media={
                str(group): tuple(Path(path) for path in paths)
                for group, paths in processed.items()
            },
            due_at=datetime.fromisoformat(row['due_at']),
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            state=str(row['state']),
            results=tuple(json.loads(row['results'])),
        )
