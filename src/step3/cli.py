from __future__ import annotations

import argparse
import os
import runpy
import sys
from typing import Optional

from .core import _MonitoringProfiler, resolve_name
from .results import FuncStats, StatsResult


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="profit",
        description=(
            "A lightweight Python profiler.\n\n"
            "Profile the whole script:\n"
            "  profit script.py\n\n"
            "Focus on specific functions:\n"
            "  profit script.py -p mymod:func1 -p mymod:func2\n\n"
            "Compare against a baseline:\n"
            "  profit script.py -b mymod:func_old -p mymod:func_new\n\n"
            "Pass arguments to the script after --:\n"
            "  profit script.py -- --script-arg val"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-p", "--profile",
        metavar="TARGET",
        action="append",
        help=(
            "A callable to show, as an importable name "
            "('mymod:MyClass.method' or 'mymod.func'). "
            "Repeat to show multiple in one table."
        ),
    )
    parser.add_argument(
        "-b", "--baseline",
        metavar="TARGET",
        help=(
            "Baseline callable for comparison. "
            "Each -p target will show a ratio relative to this."
        ),
    )
    parser.add_argument(
        "-m",
        dest="module",
        metavar="MODULE",
        help="Run a module as a script (like 'python -m module').",
    )
    parser.add_argument(
        "--sort",
        default="cumulative",
        choices=["cumulative", "tottime", "calls"],
        help="Sort key for the output table (default: cumulative).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of functions to show per profile (default: 20).",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = _build_parser()
    args, remaining = parser.parse_known_args(argv)

    if args.no_color:
        os.environ["NO_COLOR"] = "1"

    if args.module:
        target_module: Optional[str] = args.module
        target_script: Optional[str] = None
        script_args = remaining
    else:
        if not remaining:
            parser.error("No script specified. Provide a script path or use -m MODULE.")
        if remaining[0] == "--":
            remaining = remaining[1:]
        if not remaining:
            parser.error("No script specified after '--'.")
        target_script = remaining[0]
        target_module = None
        script_args = remaining[1:]
        if script_args and script_args[0] == "--":
            script_args = script_args[1:]

    old_argv = sys.argv[:]
    old_path = sys.path[:]

    if target_module:
        sys.argv = [target_module] + script_args
    else:
        sys.argv = [target_script] + script_args
        script_dir = os.path.dirname(os.path.abspath(target_script))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

    # Resolve -b / -p targets before running so import errors surface early.
    # For Python functions we store a (filename, firstlineno, qualname) key because
    # runpy.run_path re-compiles the script, producing new code objects with different
    # id()s than those we resolved before the run.
    # For C callables id() is stable (they're singletons), so we keep the object itself.
    def _resolve_key(name: str) -> object:
        # Bare identifier (no module prefix) — defer matching to post-run
        if ":" not in name and "." not in name:
            return ("__bare__", name)
        try:
            func = resolve_name(name)
        except (ImportError, AttributeError, TypeError) as exc:
            sys.exit(f"profit: cannot resolve {name!r}: {exc}")
        code = getattr(func, "__code__", None)
        if code is not None:
            return (code.co_filename, code.co_firstlineno,
                    code.co_qualname if hasattr(code, "co_qualname") else code.co_name)
        return func  # C callable — id() is stable

    baseline_target: Optional[tuple[str, object]] = None
    if args.baseline:
        baseline_target = (args.baseline, _resolve_key(args.baseline))

    profile_targets: list[tuple[str, object]] = []
    for name in (args.profile or []):
        profile_targets.append((name, _resolve_key(name)))

    profiler = _MonitoringProfiler()
    profiler.start()
    try:
        if target_module:
            runpy.run_module(target_module, run_name="__main__", alter_sys=True)
        else:
            runpy.run_path(target_script, run_name="__main__")
    finally:
        profiler.stop()
        sys.argv = old_argv
        sys.path = old_path

    from .formatting import get_formatter

    formatter = get_formatter()
    name = target_module or os.path.basename(target_script)

    if not profile_targets and not baseline_target:
        result = profiler.get_result(name, args.sort, args.limit)
        formatter.print_stats(result, main_file=target_script)
        return

    # Build ordered list: baseline first (if any), then -p targets.
    ordered: list[tuple[str, object]] = []
    baseline_idx: Optional[int] = None
    if baseline_target:
        baseline_idx = 0
        ordered.append(baseline_target)
    ordered.extend(profile_targets)

    results = [
        _extract_target_result(profiler, name, key, args.sort, args.limit, target_script)
        for name, key in ordered
    ]
    formatter.print_table(results, baseline_idx=baseline_idx, main_file=target_script)


def _extract_target_result(
    profiler: _MonitoringProfiler,
    name: str,
    key: object,
    sort: str,
    limit: int,
    script_path: Optional[str] = None,
) -> StatsResult:
    """Pull a single function's stats out of the full profiler data."""
    if isinstance(key, tuple):
        kind = key[0]
        if kind == "__bare__":
            # Bare name: match by qualname within the script file
            bare_name = key[1]
            abs_script = os.path.abspath(script_path) if script_path else None
            rec = None
            for r in profiler._py_data.values():
                code = r.func
                rq = code.co_qualname if hasattr(code, "co_qualname") else code.co_name
                if rq == bare_name and (abs_script is None or os.path.abspath(code.co_filename) == abs_script):
                    rec = r
                    break
        else:
            # Python function: key is (filename, firstlineno, qualname)
            filename, firstlineno, qualname = key
            abs_filename = os.path.abspath(filename)
            rec = None
            for r in profiler._py_data.values():
                code = r.func
                rq = code.co_qualname if hasattr(code, "co_qualname") else code.co_name
                if os.path.abspath(code.co_filename) == abs_filename and code.co_firstlineno == firstlineno and rq == qualname:
                    rec = r
                    break
        if rec is None:
            return StatsResult(target_name=name, total_time_ns=0, func_stats=[])
        code = rec.func
        fs = FuncStats(
            name=code.co_qualname if hasattr(code, "co_qualname") else code.co_name,
            file=code.co_filename,
            line=code.co_firstlineno,
            ncalls=rec.ncalls,
            tottime_ns=rec.cumtime_ns,
            cumtime_ns=rec.cumtime_ns,
            call_times_ns=rec.call_times_ns,
        )
        return StatsResult(target_name=name, total_time_ns=rec.cumtime_ns, func_stats=[fs])
    else:
        # C callable — id() is stable
        rec = profiler._c_data.get(id(key))
        if rec is None:
            return StatsResult(target_name=name, total_time_ns=0, func_stats=[])
        callable_ = rec.func
        fn_name = getattr(callable_, "__qualname__", None) or getattr(callable_, "__name__", repr(callable_))
        module = getattr(callable_, "__module__", "") or ""
        fs = FuncStats(
            name=f"{module}.{fn_name}" if module else fn_name,
            file=module,
            line=0,
            ncalls=rec.ncalls,
            tottime_ns=rec.cumtime_ns,
            cumtime_ns=rec.cumtime_ns,
            call_times_ns=rec.call_times_ns,
        )
        return StatsResult(target_name=name, total_time_ns=rec.cumtime_ns, func_stats=[fs])

if __name__ == '__main__':
    main()
