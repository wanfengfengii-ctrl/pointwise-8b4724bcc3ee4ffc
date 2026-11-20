"""Record actual arrivals and the chronological erasure of public loops."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _TraceSnapshot:
    actual: tuple[str, ...]
    retained: tuple[str, ...]
    erasures: tuple[tuple[str, tuple[str, ...]], ...]


class WalkTrace:
    def __init__(self, start):
        self._actual = [start]
        self._retained = [start]
        self._erasures = []

    def record_arrival(self, station):
        self._actual.append(station)
        if station in self._retained:
            end = self._retained.index(station) + 1
            removed = tuple(self._retained[end:])
            self._erasures.append((station, removed))
            del self._retained[end:]
        else:
            self._retained.append(station)

    def snapshot(self):
        return _TraceSnapshot(tuple(self._actual), tuple(self._retained), tuple(self._erasures))
