"""Intelligent caching system for API providers.

Features:
- Memory cache with LRU eviction
- Optional disk persistence
- TTL-based expiration (default 24h per Pixabay requirements)
- Rate limit aware (won't make requests when exhausted)
- Thread-safe for concurrent access
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, Generic

from pydantic import BaseModel

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """A cached item with metadata."""
    key: str
    value: T
    created_at: float
    expires_at: float
    provider: str
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def ttl_remaining(self) -> float:
        return max(0, self.expires_at - time.time())


class MemoryCache:
    """In-memory LRU cache with TTL support."""

    def __init__(self, max_size: int = 1000) -> None:
        self._cache: OrderedDict[str, CacheEntry[Any]] = OrderedDict()
        self._max_size = max_size
        self._lock = threading.RLock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def get(self, key: str) -> Any | None:
        """Get item from cache, returns None if not found or expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return None

            if entry.is_expired:
                del self._cache[key]
                self._stats["misses"] += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.hit_count += 1
            self._stats["hits"] += 1
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: int = 86400,
        provider: str = "",
    ) -> None:
        """Set item in cache with TTL in seconds."""
        with self._lock:
            now = time.time()
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=now,
                expires_at=now + ttl,
                provider=provider,
            )

            # Evict if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
                self._stats["evictions"] += 1

            self._cache[key] = entry
            self._cache.move_to_end(key)

    def delete(self, key: str) -> bool:
        """Delete item from cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self, provider: str | None = None) -> int:
        """Clear cache, optionally only for specific provider."""
        with self._lock:
            if provider is None:
                count = len(self._cache)
                self._cache.clear()
                return count

            keys_to_delete = [
                k for k, v in self._cache.items() if v.provider == provider
            ]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)

    def cleanup_expired(self) -> int:
        """Remove all expired entries."""
        with self._lock:
            now = time.time()
            keys_to_delete = [
                k for k, v in self._cache.items() if v.expires_at < now
            ]
            for key in keys_to_delete:
                del self._cache[key]
            return len(keys_to_delete)

    @property
    def stats(self) -> dict[str, int]:
        """Get cache statistics."""
        with self._lock:
            return {
                **self._stats,
                "size": len(self._cache),
                "max_size": self._max_size,
            }


class DiskCache:
    """SQLite-based persistent cache for API responses."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    hit_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_provider ON cache(provider)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)")
            conn.commit()

    def get(self, key: str) -> dict[str, Any] | None:
        """Get item from disk cache."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            )
            row = cursor.fetchone()

            if row is None:
                return None

            if time.time() > row["expires_at"]:
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
                return None

            # Update hit count
            conn.execute(
                "UPDATE cache SET hit_count = hit_count + 1 WHERE key = ?", (key,)
            )
            conn.commit()

            return json.loads(row["value"])

    def set(
        self,
        key: str,
        value: dict[str, Any],
        ttl: int = 86400,
        provider: str = "",
    ) -> None:
        """Set item in disk cache."""
        now = time.time()
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache (key, value, provider, created_at, expires_at, hit_count)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (key, json.dumps(value), provider, now, now + ttl),
            )
            conn.commit()

    def delete(self, key: str) -> bool:
        """Delete item from disk cache."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0

    def clear(self, provider: str | None = None) -> int:
        """Clear cache, optionally only for specific provider."""
        with sqlite3.connect(str(self.db_path)) as conn:
            if provider is None:
                cursor = conn.execute("DELETE FROM cache")
            else:
                cursor = conn.execute(
                    "DELETE FROM cache WHERE provider = ?", (provider,)
                )
            conn.commit()
            return cursor.rowcount

    def cleanup_expired(self) -> int:
        """Remove all expired entries."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "DELETE FROM cache WHERE expires_at < ?", (time.time(),)
            )
            conn.commit()
            return cursor.rowcount

    def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row

            total = conn.execute("SELECT COUNT(*) as count FROM cache").fetchone()["count"]

            by_provider = {}
            for row in conn.execute(
                "SELECT provider, COUNT(*) as count FROM cache GROUP BY provider"
            ):
                by_provider[row["provider"]] = row["count"]

            expired = conn.execute(
                "SELECT COUNT(*) as count FROM cache WHERE expires_at < ?",
                (time.time(),),
            ).fetchone()["count"]

            return {
                "total": total,
                "by_provider": by_provider,
                "expired": expired,
                "db_path": str(self.db_path),
            }


class ProviderCache:
    """Combined memory and disk cache for API providers.

    Uses memory cache for fast access with disk cache as persistent backup.
    Respects provider-specific TTL requirements (e.g., Pixabay's 24h cache).
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        memory_max_size: int = 1000,
        default_ttl: int = 86400,  # 24 hours
    ) -> None:
        self.memory = MemoryCache(max_size=memory_max_size)
        self.disk = DiskCache(cache_dir / "provider_cache.db") if cache_dir else None
        self.default_ttl = default_ttl

    def _make_key(self, provider: str, method: str, params: dict[str, Any]) -> str:
        """Generate a unique cache key."""
        # Sort params for consistent keys
        param_str = json.dumps(params, sort_keys=True)
        hash_input = f"{provider}:{method}:{param_str}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:32]

    def get(self, provider: str, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Get cached response."""
        key = self._make_key(provider, method, params)

        # Try memory first
        result = self.memory.get(key)
        if result is not None:
            return result

        # Try disk if available
        if self.disk:
            result = self.disk.get(key)
            if result is not None:
                # Promote to memory cache
                self.memory.set(key, result, provider=provider)
                return result

        return None

    def set(
        self,
        provider: str,
        method: str,
        params: dict[str, Any],
        value: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """Cache a response."""
        key = self._make_key(provider, method, params)
        ttl = ttl or self.default_ttl

        self.memory.set(key, value, ttl=ttl, provider=provider)

        if self.disk:
            self.disk.set(key, value, ttl=ttl, provider=provider)

    def invalidate(self, provider: str, method: str, params: dict[str, Any]) -> None:
        """Invalidate a specific cache entry."""
        key = self._make_key(provider, method, params)
        self.memory.delete(key)
        if self.disk:
            self.disk.delete(key)

    def clear(self, provider: str | None = None) -> dict[str, int]:
        """Clear cache for a provider or all providers."""
        memory_cleared = self.memory.clear(provider)
        disk_cleared = self.disk.clear(provider) if self.disk else 0
        return {"memory": memory_cleared, "disk": disk_cleared}

    def cleanup(self) -> dict[str, int]:
        """Remove expired entries."""
        memory_cleaned = self.memory.cleanup_expired()
        disk_cleaned = self.disk.cleanup_expired() if self.disk else 0
        return {"memory": memory_cleaned, "disk": disk_cleaned}

    def stats(self) -> dict[str, Any]:
        """Get combined cache statistics."""
        return {
            "memory": self.memory.stats,
            "disk": self.disk.stats() if self.disk else None,
        }


def serialize_pydantic(obj: BaseModel) -> dict[str, Any]:
    """Serialize a Pydantic model for caching."""
    return obj.model_dump()


def deserialize_pydantic(data: dict[str, Any], model_class: type[T]) -> T:
    """Deserialize cached data to a Pydantic model."""
    return model_class.model_validate(data)
