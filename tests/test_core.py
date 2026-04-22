"""Tests for step3.core: _MonitoringProfiler, _Record, resolve_name."""
from __future__ import annotations

import sys

import pytest

from step3.core import _MonitoringProfiler, _Record


# ---------------------------------------------------------------------------
# _Record
# ---------------------------------------------------------------------------

class TestRecord:
    def test_defaults(self):
        rec = _Record(func=None)
        assert rec.cumtime_ns == 0
        assert rec.ncalls == 0
        assert rec.entry_stack == []
        assert rec.call_times_ns == []

    def test_func_stored(self):
        sentinel = object()
        rec = _Record(func=sentinel)
        assert rec.func is sentinel


# ---------------------------------------------------------------------------
# _MonitoringProfiler — basic Python function tracking
# ---------------------------------------------------------------------------

class TestMonitoringProfilerPython:
    def test_ncalls_simple(self):
        profiler = _MonitoringProfiler()
        profiler.start()
        def add(a, b):
            return a + b
        add(1, 2)
        add(3, 4)
        profiler.stop()

        codes = {id(r.func): r for r in profiler._py_data.values()}
        add_rec = next(
            (r for r in profiler._py_data.values()
             if r.func.co_name == "add"),
            None,
        )
        assert add_rec is not None, "add() not found in _py_data"
        assert add_rec.ncalls == 2

    def test_cumtime_nonzero(self):
        import time as _time
        profiler = _MonitoringProfiler()
        profiler.start()
        def slow():
            _time.sleep(0.01)
        slow()
        profiler.stop()

        rec = next(
            (r for r in profiler._py_data.values()
             if r.func.co_name == "slow"),
            None,
        )
        assert rec is not None
        assert rec.cumtime_ns > 0

    def test_call_times_ns_populated(self):
        profiler = _MonitoringProfiler()
        profiler.start()
        def noop():
            pass
        noop()
        noop()
        noop()
        profiler.stop()

        rec = next(
            (r for r in profiler._py_data.values()
             if r.func.co_name == "noop"),
            None,
        )
        assert rec is not None
        assert len(rec.call_times_ns) == 3
        assert all(t >= 0 for t in rec.call_times_ns)

    def test_call_times_ns_all_positive(self):
        import time as _time
        profiler = _MonitoringProfiler()
        profiler.start()
        def work():
            _time.sleep(0.001)
        work()
        work()
        profiler.stop()

        rec = next(
            (r for r in profiler._py_data.values()
             if r.func.co_name == "work"),
            None,
        )
        assert rec is not None
        assert all(t > 0 for t in rec.call_times_ns)


# ---------------------------------------------------------------------------
# _MonitoringProfiler — C callable tracking
# ---------------------------------------------------------------------------

class TestMonitoringProfilerC:
    def test_builtin_sum_tracked(self):
        profiler = _MonitoringProfiler()
        profiler.start()
        result = sum([1, 2, 3])
        profiler.stop()

        assert result == 6
        # sum is a builtin — it should appear somewhere in _c_data
        c_funcs = {
            getattr(r.func, "__name__", None)
            for r in profiler._c_data.values()
        }
        assert "sum" in c_funcs, f"sum not found in C data; found: {c_funcs}"

    def test_builtin_len_tracked(self):
        profiler = _MonitoringProfiler()
        profiler.start()
        result = len([1, 2, 3])
        profiler.stop()

        assert result == 3
        c_funcs = {
            getattr(r.func, "__name__", None)
            for r in profiler._c_data.values()
        }
        assert "len" in c_funcs, f"len not found in C data; found: {c_funcs}"

    def test_c_callable_ncalls(self):
        profiler = _MonitoringProfiler()
        profiler.start()
        for _ in range(5):
            len([])
        profiler.stop()

        rec = next(
            (r for r in profiler._c_data.values()
             if getattr(r.func, "__name__", None) == "len"),
            None,
        )
        assert rec is not None
        assert rec.ncalls == 5


# ---------------------------------------------------------------------------
# _MonitoringProfiler — recursive function
# ---------------------------------------------------------------------------

class TestMonitoringProfilerRecursion:
    def test_recursive_call_times_one_entry_per_top_level_call(self):
        """call_times_ns should only record the top-level entry, not each
        recursive call.  Calling factorial(5) once should add exactly one
        entry to call_times_ns, not six (one per frame)."""
        profiler = _MonitoringProfiler()
        profiler.start()

        def factorial(n):
            if n <= 1:
                return 1
            return n * factorial(n - 1)

        factorial(5)
        factorial(3)
        profiler.stop()

        rec = next(
            (r for r in profiler._py_data.values()
             if r.func.co_name == "factorial"),
            None,
        )
        assert rec is not None
        # Each top-level call contributes exactly one entry.
        assert len(rec.call_times_ns) == 2
        # But ncalls counts every frame, including recursive ones.
        # factorial(5) → 5 frames; factorial(3) → 3 frames
        assert rec.ncalls == 5 + 3

    def test_recursive_call_times_single_invocation(self):
        profiler = _MonitoringProfiler()
        profiler.start()

        def fib(n):
            if n <= 1:
                return n
            return fib(n - 1) + fib(n - 2)

        fib(6)
        profiler.stop()

        rec = next(
            (r for r in profiler._py_data.values()
             if r.func.co_name == "fib"),
            None,
        )
        assert rec is not None
        # Single top-level call → exactly one entry.
        assert len(rec.call_times_ns) == 1


# ---------------------------------------------------------------------------
# get_result produces a StatsResult
# ---------------------------------------------------------------------------

class TestGetResult:
    def test_get_result_contains_profiled_function(self):
        profiler = _MonitoringProfiler()
        profiler.start()
        def target():
            return 42
        target()
        profiler.stop()

        result = profiler.get_result("test")
        # co_qualname includes the enclosing scope, so match by suffix
        names = [fs.name for fs in result.func_stats]
        assert any(n.endswith("target") for n in names), f"target not found in {names}"

    def test_get_result_total_time_positive(self):
        import time as _time
        profiler = _MonitoringProfiler()
        profiler.start()
        _time.sleep(0.005)
        profiler.stop()

        result = profiler.get_result("test")
        assert result.total_time_ns > 0
