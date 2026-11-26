"""A small LRU cache with a hard size limit and per-entry expiry.

Every cache in echo-tunes uses this, so memory stays flat however long the server runs:
old entries are evicted when the cache is full and expired ones are dropped on access.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable


class BoundedTTLCache[K, V]:
    def __init__(
        self, maxsize: int, ttl: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        self._maxsize = maxsize
        self._ttl = ttl
        self._clock = clock
        self._data: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if self._clock() >= expires:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: K, value: V, ttl: float | None = None) -> None:
        expires = self._clock() + (self._ttl if ttl is None else ttl)
        self._data[key] = (expires, value)
        self._data.move_to_end(key)
        while len(self._data) > self._maxsize:
            self._data.popitem(last=False)

    def pop(self, key: K) -> None:
        self._data.pop(key, None)

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: object) -> bool:
        return self.get(key) is not None  # type: ignore[arg-type]
