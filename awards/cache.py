"""Calibre-free persistent award-source cache.

The cache directory is injected by the plugin. This module never discovers
Calibre's config path. A missing directory configuration is a cache miss,
not an award-source failure: load returns None, save and invalidation are
no-ops.

Archive sources store one JSON file per source. Query-driven sources may
also store many independent keyed entries under ``<source_key>/<entry_kind>/``.
Writes serialize completely, then publish with os.replace so a failed save
cannot destroy the last good file. I/O errors while saving are swallowed:
persistent cache is an optimization, and a live lookup should still succeed.

Archive sources assign their own TTL as a 7-day base plus an explicit
per-source hour offset. This module does not know award-source order.

A lookup refresh budget lets the engine allow at most one optional
stale-but-valid archive refresh per top-level lookup_awards() call.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

CACHE_FORMAT_VERSION = 1
_SOURCE_KEY_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_-]*$')
_ENTRY_FILENAME_RE = re.compile(r'^[0-9a-f]{64}\.json$')
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
_KEYED_ENVELOPE_FIELDS = _ENVELOPE_FIELDS | frozenset({
    'entry_kind',
    'entry_key',
})

_config_lock = threading.Lock()
_cache_directory: Path | None = None
_budget_lock = threading.Lock()
_active_budget: _LookupRefreshBudget | None = None


class _LookupRefreshBudget:
    """One optional stale-refresh claim, held for an entire lookup."""

    __slots__ = ('_claimed', '_lock')

    def __init__(self) -> None:
        self._claimed = False
        self._lock = threading.Lock()

    def try_claim(self) -> bool:
        with self._lock:
            if self._claimed:
                return False
            self._claimed = True
            return True


def set_cache_directory(path: str | os.PathLike[str] | None) -> None:
    """Set or clear the persistent cache directory.

    None disables disk caching. A configured path must be absolute; this
    module never creates files outside that directory.
    """
    global _cache_directory
    resolved = None if path is None else _require_absolute_directory(path)
    with _config_lock:
        _cache_directory = resolved


def source_cache_directory(config_dir: str | os.PathLike[str]) -> Path:
    """Return ``{config_dir}/plugins/calibre_awards/source_cache``.

    The plugin layer supplies Calibre's config_dir. This helper does not
    import Calibre or create the directory.
    """
    return _require_absolute_directory(
        Path(os.fspath(config_dir)) / 'plugins' / 'calibre_awards' / 'source_cache'
    )


def configure_from_config_dir(config_dir: str | os.PathLike[str]) -> None:
    """Point the cache at the standard plugin source-cache directory."""
    set_cache_directory(source_cache_directory(config_dir))


def _reset_runtime_state() -> None:
    """Clear the injected directory and any lookup refresh budget.

    Tests only; not public plugin API.
    """
    global _active_budget
    set_cache_directory(None)
    with _budget_lock:
        _active_budget = None


@contextmanager
def lookup_refresh_budget():
    """Bind a one-claim stale-refresh budget to one top-level lookup.

    The claim stays consumed until this context exits, not merely for one
    network request. Concurrent source workers share the same budget object.
    Nested contexts restore the previous budget on exit. Standalone source
    lookups with no active budget are unrestricted.
    """
    global _active_budget
    budget = _LookupRefreshBudget()
    with _budget_lock:
        previous = _active_budget
        _active_budget = budget
    try:
        yield
    finally:
        with _budget_lock:
            if _active_budget is budget:
                _active_budget = previous


def try_claim_stale_refresh() -> bool:
    """Return True if this caller may live-refresh stale-but-valid cache.

    At most one successful claim is granted per active lookup_refresh_budget.
    With no active budget, always returns True so standalone source lookups
    keep their existing refresh behavior.

    Call this only for optional refresh of a usable stale archive. Fresh
    caches and missing or invalid caches must not consume the slot.
    """
    with _budget_lock:
        budget = _active_budget
    if budget is None:
        return True
    return budget.try_claim()


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
    encoded = _encode_cache_json(payload)
    directory = _configured_directory()
    if directory is None:
        return
    _atomic_write_json(
        directory,
        _cache_path(directory, key),
        encoded,
        tmp_prefix=f'{key}.',
    )


def load_cache_entry(
    source_key: str,
    entry_kind: str,
    entry_key: str,
    source_cache_version: int,
) -> dict | None:
    """Return a validated keyed-entry envelope, or None on miss/incompatibility.

    Stale-but-valid files still load. The hashed filename is not identity:
    stored entry_key must exactly match the requested logical key.
    """
    if not _is_safe_source_key(source_key):
        return None
    if not _is_safe_entry_kind(entry_kind):
        return None
    if not _is_usable_entry_key(entry_key):
        return None
    if not _is_usable_version(source_cache_version):
        return None
    directory = _configured_directory()
    if directory is None:
        return None
    path = _entry_cache_path(directory, source_key, entry_kind, entry_key)
    if path is None:
        return None
    try:
        raw = path.read_text(encoding='utf-8')
    except OSError:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return _validated_keyed_payload(
        payload,
        source_key,
        entry_kind,
        entry_key,
        source_cache_version,
    )


def save_cache_entry(
    source_key: str,
    entry_kind: str,
    entry_key: str,
    source_cache_version: int,
    *,
    records,
    source_urls,
    coverage,
    ttl_seconds: int,
    generated_at: datetime | None = None,
) -> None:
    """Atomically write one keyed cache entry.

    Programmer errors raise. Filesystem errors leave any previous good file
    in place and do not propagate.
    """
    key = _require_safe_source_key(source_key)
    kind = _require_safe_entry_kind(entry_kind)
    logical_key = _require_entry_key(entry_key)
    version = _require_usable_version(source_cache_version)
    record_list = _require_records(records)
    urls = _require_source_urls(source_urls)
    ttl = _require_ttl_seconds(ttl_seconds)
    coverage_value = _require_json_value(coverage, field_name='coverage')
    generated = _require_generated_at(generated_at)
    payload = {
        'cache_format_version': CACHE_FORMAT_VERSION,
        'coverage': coverage_value,
        'entry_key': logical_key,
        'entry_kind': kind,
        'generated_at': _format_generated_at(generated),
        'record_count': len(record_list),
        'records': record_list,
        'source_cache_version': version,
        'source_key': key,
        'source_urls': urls,
        'ttl_seconds': ttl,
    }
    encoded = _encode_cache_json(payload)
    directory = _configured_directory()
    if directory is None:
        return
    final_path = _entry_cache_path(directory, key, kind, logical_key)
    if final_path is None:
        return
    _atomic_write_json(
        final_path.parent,
        final_path,
        encoded,
        tmp_prefix=f'{_entry_key_digest(logical_key)[:8]}.',
    )


def invalidate_cache_entry(
    source_key: str,
    entry_kind: str,
    entry_key: str,
) -> None:
    """Remove one keyed entry file. Missing files and unsafe keys are no-ops."""
    if not _is_safe_source_key(source_key):
        return
    if not _is_safe_entry_kind(entry_kind):
        return
    if not _is_usable_entry_key(entry_key):
        return
    directory = _configured_directory()
    if directory is None:
        return
    path = _entry_cache_path(directory, source_key, entry_kind, entry_key)
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass


def invalidate_source_cache(source_key: str) -> bool:
    """Remove one source's archive file and any keyed-entry subtree.

    Returns True when all managed cache data for that source is absent
    afterwards, including when there was nothing to remove. Returns False
    if at least one managed archive or keyed file remains. Ordinary
    filesystem errors are swallowed and do not raise.

    Missing files, missing directories, an unconfigured cache directory,
    and unsafe keys are treated as success. Other sources and unrelated
    cache-directory files are left in place and do not count as failure.
    """
    if not _is_safe_source_key(source_key):
        return True
    directory = _configured_directory()
    if directory is None:
        return True
    archive_path = _cache_path(directory, source_key)
    _unlink_quietly(archive_path)
    keyed_cleared = _invalidate_keyed_source_tree(directory / source_key)
    return (not _is_existing_file(archive_path)) and keyed_cleared


def invalidate_all_source_caches() -> None:
    """Remove owned top-level source JSON files and managed keyed trees.

    Does not recursively wipe the cache directory. Unrelated names, including
    non-JSON files and non-source directories, are left in place.
    """
    directory = _configured_directory()
    if directory is None or not directory.is_dir():
        return
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        path = directory / name
        stem, ext = os.path.splitext(name)
        if ext == '.json' and _is_safe_source_key(stem) and path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
            continue
        if path.is_dir() and _is_safe_source_key(name):
            _invalidate_keyed_source_tree(path)


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


def _is_safe_entry_kind(entry_kind: str) -> bool:
    return _is_safe_source_key(entry_kind)


def _require_safe_entry_kind(entry_kind: str) -> str:
    if not _is_safe_entry_kind(entry_kind):
        raise ValueError(
            'entry_kind must be a letter followed by letters, digits, '
            'underscores, or hyphens'
        )
    return entry_kind


def _is_usable_entry_key(entry_key: str) -> bool:
    return (
        isinstance(entry_key, str)
        and bool(entry_key)
        and entry_key == entry_key.strip()
    )


def _require_entry_key(entry_key: str) -> str:
    if not _is_usable_entry_key(entry_key):
        raise ValueError('entry_key must be a non-empty string without surrounding whitespace')
    return entry_key


def _entry_key_digest(entry_key: str) -> str:
    return hashlib.sha256(entry_key.encode('utf-8')).hexdigest()


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


def _entry_cache_path(
    directory: Path,
    source_key: str,
    entry_kind: str,
    entry_key: str,
) -> Path | None:
    filename = f'{_entry_key_digest(entry_key)}.json'
    path = directory / source_key / entry_kind / filename
    if not _path_is_within(path, directory):
        return None
    return path


def _path_is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return True


def _encode_cache_json(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode('utf-8') + b'\n'


def _atomic_write_json(
    directory: Path,
    final_path: Path,
    encoded: bytes,
    *,
    tmp_prefix: str,
) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    fd, tmp_path = tempfile.mkstemp(
        prefix=tmp_prefix,
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


def _is_managed_entry_filename(name: str) -> bool:
    return bool(_ENTRY_FILENAME_RE.fullmatch(name))


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _is_existing_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return True


def _managed_keyed_files_remain(source_dir: Path) -> bool:
    """Return True if any managed keyed JSON file is still present.

    Unrelated names are ignored. If the tree cannot be listed, treat managed
    files as still present so callers cannot claim a successful wipe.
    """
    if not source_dir.is_dir():
        return False
    try:
        names = os.listdir(source_dir)
    except OSError:
        return True
    for name in names:
        kind_dir = source_dir / name
        if not kind_dir.is_dir() or not _is_safe_entry_kind(name):
            continue
        try:
            filenames = os.listdir(kind_dir)
        except OSError:
            return True
        for filename in filenames:
            if not _is_managed_entry_filename(filename):
                continue
            if _is_existing_file(kind_dir / filename):
                return True
    return False


def _invalidate_keyed_source_tree(source_dir: Path) -> bool:
    """Remove managed hashed entry files under one source directory.

    Only ``<safe-kind>/<64-hex>.json`` files are deleted. Unrelated files and
    directories are left in place. Empty managed kind directories, and then an
    empty source directory, are removed when possible.

    Returns True when no managed keyed files remain. Remaining unrelated
    files do not count as failure.
    """
    if not source_dir.is_dir():
        return True
    try:
        names = os.listdir(source_dir)
    except OSError:
        return not _managed_keyed_files_remain(source_dir)
    for name in names:
        kind_dir = source_dir / name
        if not kind_dir.is_dir() or not _is_safe_entry_kind(name):
            continue
        try:
            filenames = os.listdir(kind_dir)
        except OSError:
            continue
        for filename in filenames:
            if not _is_managed_entry_filename(filename):
                continue
            path = kind_dir / filename
            if not path.is_file():
                continue
            _unlink_quietly(path)
        try:
            os.rmdir(kind_dir)
        except OSError:
            pass
    try:
        os.rmdir(source_dir)
    except OSError:
        pass
    return not _managed_keyed_files_remain(source_dir)


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


def _validated_keyed_payload(
    payload,
    source_key: str,
    entry_kind: str,
    entry_key: str,
    source_cache_version: int,
) -> dict | None:
    if not isinstance(payload, dict):
        return None
    if set(payload) != _KEYED_ENVELOPE_FIELDS:
        return None
    if payload.get('cache_format_version') != CACHE_FORMAT_VERSION:
        return None
    if payload.get('source_key') != source_key:
        return None
    if payload.get('entry_kind') != entry_kind:
        return None
    if payload.get('entry_key') != entry_key:
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
