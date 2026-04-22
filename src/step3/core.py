from __future__ import annotations

import os
import pkgutil
import sys
import time
import types
from dataclasses import dataclass, field
from typing import Callable, Generic, Optional, TypeVar

from .results import FuncStats, StatsResult

_F = TypeVar("_F")


@dataclass
class _Record(Generic[_F]):
    func: _F
    cumtime_ns: int = 0
    entry_stack: list[int] = field(default_factory=list)
    ncalls: int = 0
    call_times_ns: list[int] = field(default_factory=list)


class _MonitoringProfiler:
    """Lightweight profiler using sys.monitoring (Python 3.12+).

    Tracks all Python function calls and C extension calls within a block,
    measuring cumulative wall time per function.
    """

    _TOOL_ID = sys.monitoring.PROFILER_ID

    def __init__(self):
        self._py_data: dict[int, _Record[types.CodeType]] = {}
        self._c_data: dict[int, _Record[Callable]] = {}
        self._start_ns: int = 0
        self._total_ns: int = 0

    def start(self) -> None:
        m = sys.monitoring
        m.use_tool_id(self._TOOL_ID, "step3")
        m.set_events(
            self._TOOL_ID,
            m.events.PY_START | m.events.PY_RETURN | m.events.RAISE
            | m.events.CALL | m.events.C_RETURN | m.events.C_RAISE,
        )
        m.register_callback(self._TOOL_ID, m.events.PY_START, self._on_py_start)
        m.register_callback(self._TOOL_ID, m.events.PY_RETURN, self._on_py_exit)
        m.register_callback(self._TOOL_ID, m.events.RAISE, self._on_py_exit)
        m.register_callback(self._TOOL_ID, m.events.CALL, self._on_call)
        m.register_callback(self._TOOL_ID, m.events.C_RETURN, self._on_c_return)
        m.register_callback(self._TOOL_ID, m.events.C_RAISE, self._on_c_return)
        self._start_ns = time.perf_counter_ns()

    def stop(self) -> None:
        self._total_ns += time.perf_counter_ns() - self._start_ns
        m = sys.monitoring
        m.set_events(self._TOOL_ID, m.events.NO_EVENTS)
        m.free_tool_id(self._TOOL_ID)

    # -- Python frame events --

    def _on_py_start(self, code, instruction_offset: int) -> None:
        cid = id(code)
        t = time.perf_counter_ns()
        if cid not in self._py_data:
            self._py_data[cid] = _Record(func=code)
        rec = self._py_data[cid]
        rec.entry_stack.append(t)
        rec.ncalls += 1

    def _on_py_exit(self, code, instruction_offset: int, _retval: object) -> None:
        rec = self._py_data.get(id(code))
        if rec and rec.entry_stack:
            elapsed = time.perf_counter_ns() - rec.entry_stack.pop()
            rec.cumtime_ns += elapsed
            if not rec.entry_stack:  # only record when fully unwound (top-level call exit)
                rec.call_times_ns.append(elapsed)

    # -- C extension events --

    def _on_call(self, code, instruction_offset: int, callable_: object, arg0: object) -> None:
        # Only track C callables; Python calls are handled via PY_START.
        if isinstance(callable_, type) or not hasattr(callable_, "__code__"):
            cid = id(callable_)
            t = time.perf_counter_ns()
            if cid not in self._c_data:
                self._c_data[cid] = _Record(func=callable_)
            rec = self._c_data[cid]
            rec.entry_stack.append(t)
            rec.ncalls += 1

    def _on_c_return(self, code, instruction_offset: int, callable_: object, retval: object) -> None:
        cid = id(callable_)
        rec = self._c_data.get(cid)
        if rec and rec.entry_stack:
            elapsed = time.perf_counter_ns() - rec.entry_stack.pop()
            rec.cumtime_ns += elapsed
            if not rec.entry_stack:
                rec.call_times_ns.append(elapsed)

    def get_result(self, name: str, sort: str = "cumulative", limit: int = 20) -> StatsResult:
        func_stats = self._build_py_stats()
        func_stats += self._build_c_stats()

        sort_fn = {
            "cumulative": lambda fs: fs.cumtime_ns,
            "cumtime": lambda fs: fs.cumtime_ns,
            "tottime": lambda fs: fs.tottime_ns,
            "time": lambda fs: fs.tottime_ns,
            "calls": lambda fs: fs.ncalls,
            "ncalls": lambda fs: fs.ncalls,
        }.get(sort, lambda fs: fs.cumtime_ns)

        func_stats.sort(key=sort_fn, reverse=True)
        func_stats = func_stats[:limit]

        return StatsResult(
            target_name=name,
            total_time_ns=self._total_ns,
            func_stats=func_stats,
        )

    def _build_py_stats(self) -> list[FuncStats]:
        _self_dir = os.path.dirname(__file__)
        result = []
        for rec in self._py_data.values():
            code = rec.func
            if rec.ncalls == 0 or code.co_filename.startswith(_self_dir):
                continue
            result.append(FuncStats(
                name=code.co_qualname if hasattr(code, "co_qualname") else code.co_name,
                file=code.co_filename,
                line=code.co_firstlineno,
                ncalls=rec.ncalls,
                tottime_ns=rec.cumtime_ns,
                cumtime_ns=rec.cumtime_ns,
                call_times_ns=rec.call_times_ns,
            ))
        return result

    _SKIP_C = frozenset({
        id(time.perf_counter_ns),
        id(sys.monitoring.set_events),
        id(sys.monitoring.free_tool_id),
        id(sys.monitoring.register_callback),
        id(sys.monitoring.use_tool_id),
    })

    def _build_c_stats(self) -> list[FuncStats]:
        result = []
        for rec in self._c_data.values():
            callable_ = rec.func
            if rec.ncalls == 0 or id(callable_) in self._SKIP_C:
                continue
            name = getattr(callable_, "__qualname__", None) or getattr(callable_, "__name__", repr(callable_))
            module = getattr(callable_, "__module__", "") or ""
            result.append(FuncStats(
                name=f"{module}.{name}" if module else name,
                file=module,
                line=0,
                ncalls=rec.ncalls,
                tottime_ns=rec.cumtime_ns,
                cumtime_ns=rec.cumtime_ns,
                call_times_ns=rec.call_times_ns,
            ))
        return result


def resolve_name(name: str) -> Callable:
    """Resolve a dotted/colon name to a callable using pkgutil.resolve_name."""
    obj = pkgutil.resolve_name(name)
    if not callable(obj):
        raise TypeError(f"{name!r} resolves to a non-callable: {type(obj)}")
    return obj


class _Profit:
    """A lightweight profiler usable as a decorator or context manager.

    **Decorator**::

        @profit
        def my_func():
            ...

        my_func()
        profit.print_stats()

    **Context manager**::

        with profit as p:
            do_work()
        p.print_stats()
    """

    sort: str = "cumulative"
    limit: int = 20

    def __init__(self) -> None:
        self._monitoring: Optional[_MonitoringProfiler] = None
        self._name: str = "block"

    def __call__(self, func: Callable) -> Callable:
        import functools

        profiler = _MonitoringProfiler()
        self._monitoring = profiler
        self._name = getattr(func, "__qualname__", func.__name__)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            profiler.start()
            try:
                return func(*args, **kwargs)
            finally:
                profiler.stop()

        return wrapper

    def __enter__(self) -> _Profit:
        self._monitoring = _MonitoringProfiler()
        self._monitoring.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._monitoring is not None:
            self._monitoring.stop()
        return False

    def get_results(self) -> list[StatsResult]:
        if self._monitoring is None:
            return []
        return [self._monitoring.get_result(self._name, self.sort, self.limit)]

    def print_stats(self) -> None:
        from .formatting import get_formatter

        results = self.get_results()
        if not results:
            print("No profiling data collected.")
            return
        get_formatter().print_stats(results[0])


profit = _Profit()
