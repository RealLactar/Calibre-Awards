"""Calibre-free persistent award-source archive cache.

The cache directory is injected by the plugin. This module never discovers
Calibre's config path. A missing directory configuration is a cache miss,
not an award-source failure: load returns None, save and invalidation are
no-ops.

JSON files are one source per file. Writes serialize completely, then
publish with os.replace so a failed save cannot destroy the last good file.
I/O errors while saving are swallowed: persistent cache is an optimization,
and a live lookup should still succeed.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_FORMAT_VERSION = 1
_SOURCE_KEY_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_-]*$')
_ENVELOPE_FIELDS = frozenset({
    'cache_format_version',
    'source_key',
    'source_cache_version',
    'generated_at',
    'ttl_seconds',
    'source_urls',
    'record_count',
    'coverage',
    'records',
})

_config_lock = threading.Lock()
_cache_directory: Path | None = None


def set_cache_directory(path: str | os.PathLike[str] | None) -> None:
    """Set or clear the persistent cache directory.

    None disables disk caching. A configured path must be absolute; this
    module never creates files outside that directory.
    """
    global _cache_directory
    resolved = None if path is None else _require_absolute_directory(path)
    with _config_lock:
        _cache_directory = resolved


def _reset_runtime_state() -> None:
    """Clear the injected directory. Tests only; not public plugin API."""
    set_cache_directory(None)


def load_source_cache(
    source_key: str,
    source_cache_version: int,
) -> dict | None:
    """Return a validated cache envelope, or None on miss/incompatibility.

    Stale-but-valid files still load. Version mismatches and corrupt JSON
    are misses, not exceptions.
    """
    if not _is_safe_source_key(source_key):
        return None
    if not _is_usable_version(source_cache_version):
        return None
    directory = _configured_directory()
    if directory is None:
        return None
    path = _cache_path(directory, source_key)
    try:
        raw = path.read_text(encoding='utf-8')
    except OSError:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return _validated_payload(payload, source_key, source_cache_version)


def save_source_cache(
    source_key: str,
    source_cache_version: int,
    *,
    records,
    source_urls,
    coverage,
    ttl_seconds: int,
    generated_at: datetime | None = None,
) -> None:
    """Atomically write one source cache file.

    Programmer errors (unsafe key, unusable arguments, non-JSON records)
    raise. Filesystem errors leave any previous good file in place and do
    not propagate: a live award lookup must still succeed.
    """
    key = _require_safe_source_key(source_key)
    version = _require_usable_version(source_cache_version)
    record_list = _require_records(records)
    urls = _require_source_urls(source_urls)
    ttl = _require_ttl_seconds(ttl_seconds)
    coverage_value = _require_json_value(coverage, field_name='coverage')
    generated = _require_generated_at(generated_at)
    directory = _configured_directory()
    if directory is None:
        return

    payload = {
        'cache_format_version': CACHE_FORMAT_VERSION,
        'coverage': coverage_value,
        'generated_at': _format_generated_at(generated),
        'record_count': len(record_list),
        'records': record_list,
        'source_cache_version': version,
        'source_key': key,
        'source_urls': urls,
        'ttl_seconds': ttl,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode('utf-8') + b'\n'

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return

    final_path = _cache_path(directory, key)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f'{key}.',
        suffix='.json.tmp',
        dir=str(directory),
    )
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, final_path)
    except OSError:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def invalidate_source_cache(source_key: str) -> None:
    """Remove one source JSON file. Missing files and unsafe keys are no-ops."""
    if not _is_safe_source_key(source_key):
        return
    directory = _configured_directory()
    if directory is None:
        return
    try:
        _cache_path(directory, source_key).unlink()
    except OSError:
        pass


def invalidate_all_source_caches() -> None:
    """Remove owned ``<source_key>.json`` files in the configured directory.

    Does not recurse. Unrelated names, including non-JSON files, are left
    in place.
    """
    directory = _configured_directory()
    if directory is None or not directory.is_dir():
        return
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        stem, ext = os.path.splitext(name)
        if ext != '.json' or not _is_safe_source_key(stem):
            continue
        path = directory / name
        if not path.is_file():
            continue
        try:
            path.unlink()
        except OSError:
            pass


def cache_is_fresh(payload: dict, *, now: datetime | None = None) -> bool:
    """Return True while now is strictly before generated_at + ttl_seconds.

    At the exact expiry instant the payload is stale. An unusable payload
    is treated as not fresh rather than raised.
    """
    generated = _parse_generated_at(
        payload.get('generated_at') if isinstance(payload, dict) else None
    )
    ttl = _optional_ttl_seconds(
        payload.get('ttl_seconds') if isinstance(payload, dict) else None
    )
    if generated is None or ttl is None:
        return False
    current = _require_utc_datetime(now, field_name='now') if now is not None else (
        datetime.now(timezone.utc)
    )
    return current < generated + timedelta(seconds=ttl)


def _configured_directory() -> Path | None:
    with _config_lock:
        return _cache_directory


def _require_absolute_directory(path: str | os.PathLike[str]) -> Path:
    text = os.fspath(path)
    if not isinstance(text, str) or not text.strip():
        raise ValueError('cache directory must be an absolute path')
    directory = Path(text)
    if not directory.is_absolute():
        raise ValueError('cache directory must be an absolute path')
    return directory


def _is_safe_source_key(source_key: str) -> bool:
    return isinstance(source_key, str) and bool(_SOURCE_KEY_RE.fullmatch(source_key))


def _require_safe_source_key(source_key: str) -> str:
    if not _is_safe_source_key(source_key):
        raise ValueError(
            'source_key must be a letter followed by letters, digits, '
            'underscores, or hyphens'
        )
    return source_key


def _is_usable_version(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_usable_version(value) -> int:
    if not _is_usable_version(value):
        raise ValueError('source_cache_version must be an int')
    return value


def _require_records(records) -> list:
    if isinstance(records, list):
        return records
    if isinstance(records, tuple):
        return list(records)
    raise ValueError('records must be a list or tuple')


def _require_source_urls(source_urls) -> list[str]:
    if isinstance(source_urls, (str, bytes, bytearray)):
        raise ValueError('source_urls must be a sequence of strings')
    try:
        items = list(source_urls)
    except TypeError as exc:
        raise ValueError('source_urls must be a sequence of strings') from exc
    urls: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            raise ValueError('source_urls must contain non-empty strings')
        urls.append(item)
    return urls


def _require_ttl_seconds(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError('ttl_seconds must be an int greater than or equal to zero')
    return value


def _optional_ttl_seconds(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _require_json_value(value, *, field_name: str):
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} must be JSON-serializable') from exc
    return value


def _require_generated_at(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    return _require_utc_datetime(value, field_name='generated_at')


def _require_utc_datetime(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f'{field_name} must be a timezone-aware UTC datetime')
    if value.tzinfo is None:
        raise ValueError(f'{field_name} must be a timezone-aware UTC datetime')
    return value.astimezone(timezone.utc)


def _format_generated_at(value: datetime) -> str:
    utc = value.astimezone(timezone.utc).replace(microsecond=0)
    return utc.isoformat().replace('+00:00', 'Z')


def _parse_generated_at(value) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _cache_path(directory: Path, source_key: str) -> Path:
    return directory / f'{source_key}.json'


def _validated_payload(
    payload,
    source_key: str,
    source_cache_version: int,
) -> dict | None:
    if not isinstance(payload, dict):
        return None
    if set(payload) != _ENVELOPE_FIELDS:
        return None
    if payload.get('cache_format_version') != CACHE_FORMAT_VERSION:
        return None
    if payload.get('source_key') != source_key:
        return None
    if payload.get('source_cache_version') != source_cache_version:
        return None
    if not _is_usable_version(payload.get('source_cache_version')):
        return None
    generated = _parse_generated_at(payload.get('generated_at'))
    if generated is None:
        return None
    ttl = _optional_ttl_seconds(payload.get('ttl_seconds'))
    if ttl is None:
        return None
    urls = payload.get('source_urls')
    if not isinstance(urls, list) or any(
        not isinstance(item, str) or not item.strip() or item != item.strip()
        for item in urls
    ):
        return None
    records = payload.get('records')
    if not isinstance(records, list):
        return None
    record_count = payload.get('record_count')
    if not _is_usable_version(record_count) or record_count != len(records):
        return None
    if 'coverage' not in payload:
        return None
    try:
        json.dumps(payload['coverage'])
    except (TypeError, ValueError):
        return None
    return payload
