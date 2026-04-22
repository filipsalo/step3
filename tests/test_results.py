"""Tests for step3.results: FuncStats properties and _pct helper."""
from __future__ import annotations

import math

import pytest

from step3.results import FuncStats, _pct


def make_func_stats(call_times_ns: list[int], **kwargs) -> FuncStats:
    defaults = dict(
        name="test_func",
        file="test.py",
        line=1,
        ncalls=len(call_times_ns),
        tottime_ns=sum(call_times_ns),
        cumtime_ns=sum(call_times_ns),
        call_times_ns=call_times_ns,
    )
    defaults.update(kwargs)
    return FuncStats(**defaults)


# ---------------------------------------------------------------------------
# FuncStats — time properties with known values
# ---------------------------------------------------------------------------

class TestFuncStatsTimeProperties:
    def test_min_time(self):
        fs = make_func_stats([1_000, 2_000, 3_000])
        assert fs.min_time == pytest.approx(1_000 / 1e9)

    def test_max_time(self):
        fs = make_func_stats([1_000, 2_000, 3_000])
        assert fs.max_time == pytest.approx(3_000 / 1e9)

    def test_mean_time(self):
        fs = make_func_stats([1_000, 2_000, 3_000])
        assert fs.mean_time == pytest.approx(2_000 / 1e9)

    def test_mean_time_single_value(self):
        fs = make_func_stats([5_000])
        assert fs.mean_time == pytest.approx(5_000 / 1e9)

    def test_stddev_time_known_values(self):
        # Two values: stddev = |a - b| / sqrt(2) (sample stddev with ddof=1)
        a, b = 1_000, 3_000
        fs = make_func_stats([a, b])
        expected = math.sqrt(((a - 2000) ** 2 + (b - 2000) ** 2) / 1) / 1e9
        assert fs.stddev_time == pytest.approx(expected, rel=1e-9)

    def test_stddev_time_four_values(self):
        values = [100, 200, 300, 400]
        fs = make_func_stats(values)
        mean = sum(values) / len(values)
        expected_variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        expected = math.sqrt(expected_variance) / 1e9
        assert fs.stddev_time == pytest.approx(expected, rel=1e-9)

    def test_stddev_time_none_when_zero_calls(self):
        fs = make_func_stats([], ncalls=0, tottime_ns=0, cumtime_ns=0)
        assert fs.stddev_time is None

    def test_stddev_time_none_when_one_call(self):
        fs = make_func_stats([1_000])
        assert fs.stddev_time is None

    def test_min_time_none_when_empty(self):
        fs = make_func_stats([], ncalls=0, tottime_ns=0, cumtime_ns=0)
        assert fs.min_time is None

    def test_max_time_none_when_empty(self):
        fs = make_func_stats([], ncalls=0, tottime_ns=0, cumtime_ns=0)
        assert fs.max_time is None

    def test_mean_time_none_when_empty(self):
        fs = make_func_stats([], ncalls=0, tottime_ns=0, cumtime_ns=0)
        assert fs.mean_time is None


# ---------------------------------------------------------------------------
# FuncStats — tottime / cumtime conversions
# ---------------------------------------------------------------------------

class TestFuncStatsTimes:
    def test_tottime(self):
        fs = make_func_stats([1_000_000_000])  # 1 s in ns
        assert fs.tottime == pytest.approx(1.0)

    def test_cumtime(self):
        fs = make_func_stats([500_000_000])
        assert fs.cumtime == pytest.approx(0.5)

    def test_tottime_per_call(self):
        fs = make_func_stats([1_000, 3_000])  # total = 4000 ns, ncalls = 2
        assert fs.tottime_per_call == pytest.approx(4_000 / 2 / 1e9)

    def test_cumtime_per_call_zero_ncalls(self):
        fs = make_func_stats([], ncalls=0, tottime_ns=0, cumtime_ns=0)
        assert fs.cumtime_per_call is None

    def test_tottime_per_call_zero_ncalls(self):
        fs = make_func_stats([], ncalls=0, tottime_ns=0, cumtime_ns=0)
        assert fs.tottime_per_call is None


# ---------------------------------------------------------------------------
# _pct helper
# ---------------------------------------------------------------------------

class TestPct:
    def test_positive_change(self):
        # new=200, old=100 → 100 %
        assert _pct(200.0, 100.0) == pytest.approx(100.0)

    def test_negative_change(self):
        # new=50, old=100 → -50 %
        assert _pct(50.0, 100.0) == pytest.approx(-50.0)

    def test_no_change(self):
        assert _pct(42.0, 42.0) == pytest.approx(0.0)

    def test_division_by_zero_returns_none(self):
        assert _pct(5.0, 0.0) is None

    def test_new_is_none_returns_none(self):
        assert _pct(None, 100.0) is None

    def test_old_is_none_returns_none(self):
        assert _pct(100.0, None) is None

    def test_both_none_returns_none(self):
        assert _pct(None, None) is None

    def test_fractional_change(self):
        assert _pct(1.5, 1.0) == pytest.approx(50.0)
