from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FuncStats:
    name: str
    file: str
    line: int
    ncalls: int
    tottime_ns: int
    cumtime_ns: int
    call_times_ns: list[int] = field(default_factory=list)

    @property
    def tottime(self) -> float:
        return self.tottime_ns / 1e9

    @property
    def cumtime(self) -> float:
        return self.cumtime_ns / 1e9

    @property
    def tottime_per_call(self) -> Optional[float]:
        if self.ncalls == 0:
            return None
        return self.tottime / self.ncalls

    @property
    def cumtime_per_call(self) -> Optional[float]:
        if self.ncalls == 0:
            return None
        return self.cumtime / self.ncalls

    @property
    def min_time(self) -> Optional[float]:
        if not self.call_times_ns:
            return None
        return min(self.call_times_ns) / 1e9

    @property
    def max_time(self) -> Optional[float]:
        if not self.call_times_ns:
            return None
        return max(self.call_times_ns) / 1e9

    @property
    def mean_time(self) -> Optional[float]:
        if not self.call_times_ns:
            return None
        return sum(self.call_times_ns) / len(self.call_times_ns) / 1e9

    @property
    def stddev_time(self) -> Optional[float]:
        if len(self.call_times_ns) < 2:
            return None
        mean = sum(self.call_times_ns) / len(self.call_times_ns)
        variance = sum((t - mean) ** 2 for t in self.call_times_ns) / (len(self.call_times_ns) - 1)
        return math.sqrt(variance) / 1e9


@dataclass
class StatsResult:
    target_name: str
    total_time_ns: int
    func_stats: list[FuncStats]

    @property
    def total_time(self) -> float:
        return self.total_time_ns / 1e9


def _pct(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None or old == 0:
        return None
    return (new - old) / old * 100
