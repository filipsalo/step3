"""Tests for step3.formatting: _fmt_time, _ratio_str, _func_label, PlainFormatter."""
from __future__ import annotations

import io
import os
import sys
from unittest.mock import patch

import pytest

from step3.formatting import (
    PlainFormatter,
    _fmt_time,
    _func_label,
    _ratio_str,
)
from step3.results import FuncStats, StatsResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_fs(
    name: str = "func",
    file: str = "mod.py",
    line: int = 1,
    ncalls: int = 1,
    call_times_ns: list[int] | None = None,
) -> FuncStats:
    times = call_times_ns if call_times_ns is not None else [1_000_000]
    total = sum(times)
    return FuncStats(
        name=name,
        file=file,
        line=line,
        ncalls=ncalls,
        tottime_ns=total,
        cumtime_ns=total,
        call_times_ns=times,
    )


def make_result(fs: FuncStats, name: str = "run") -> StatsResult:
    return StatsResult(
        target_name=name,
        total_time_ns=fs.cumtime_ns,
        func_stats=[fs],
    )


def capture_plain_table(
    results: list[StatsResult],
    baseline_idx: int | None,
) -> str:
    """Run PlainFormatter.print_table with color disabled, return stdout."""
    buf = io.StringIO()
    with patch.dict(os.environ, {"NO_COLOR": "1"}):
        formatter = PlainFormatter()
        with patch("sys.stdout", buf):
            formatter.print_table(results, baseline_idx=baseline_idx)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# _fmt_time
# ---------------------------------------------------------------------------

class TestFmtTime:
    def test_zero(self):
        assert _fmt_time(0) == "0 s"

    def test_seconds(self):
        assert _fmt_time(1.0) == "1 s"
        assert _fmt_time(2.7) == "3 s"

    def test_milliseconds(self):
        assert _fmt_time(0.001) == "1 ms"
        assert _fmt_time(0.0015) == "2 ms"
        assert _fmt_time(0.999e-3) == "999 μs"

    def test_microseconds(self):
        assert _fmt_time(1e-6) == "1 μs"
        assert _fmt_time(500e-6) == "500 μs"

    def test_nanoseconds(self):
        assert _fmt_time(1e-9) == "1 ns"
        assert _fmt_time(250e-9) == "250 ns"

    def test_boundary_ms_to_s(self):
        # Exactly 1 second
        assert _fmt_time(1.0) == "1 s"

    def test_boundary_us_to_ms(self):
        # Exactly 1 ms
        assert _fmt_time(1e-3) == "1 ms"

    def test_boundary_ns_to_us(self):
        # Exactly 1 µs
        assert _fmt_time(1e-6) == "1 μs"

    def test_large_seconds(self):
        assert _fmt_time(100.0) == "100 s"

    def test_negative_value_scaled_correctly(self):
        # Negative values: abs used for unit selection
        result = _fmt_time(-0.001)
        assert result == "-1 ms"


# ---------------------------------------------------------------------------
# _ratio_str
# ---------------------------------------------------------------------------

class TestRatioStr:
    def test_none_returns_empty(self):
        assert _ratio_str(None) == ""

    def test_no_change(self):
        # 0 % → ratio = 1.0 → "1.00x"
        assert _ratio_str(0) == "1.00x"

    def test_positive_small(self):
        # 20 % increase → ratio = 1.20 → "1.20x"
        assert _ratio_str(20) == "1.20x"

    def test_negative_small(self):
        # -50 % → ratio = 0.50 → "0.50x"
        assert _ratio_str(-50) == "0.50x"

    def test_large_ratio(self):
        # 1000 % → ratio = 11 → "11.0x"
        assert _ratio_str(1000) == "11.0x"

    def test_very_large_ratio(self):
        # 9900 % → ratio = 100 → "100x"
        assert _ratio_str(9900) == "100x"

    def test_no_scientific_notation_small_ratio(self):
        # ratio = 0.0014 — should not use scientific notation
        # pct = (0.0014 - 1) * 100 = -99.86
        pct = (0.0014 - 1) * 100  # ≈ -99.86
        result = _ratio_str(pct)
        assert "e" not in result.lower(), f"scientific notation in: {result}"
        assert "x" in result

    def test_two_decimal_places_in_normal_range(self):
        result = _ratio_str(50)  # ratio = 1.50
        assert result == "1.50x"

    def test_one_decimal_place_above_ten(self):
        result = _ratio_str(500)  # ratio = 6.0 — between 1 and 10 (actually 6)
        assert result == "6.00x"

    def test_above_ten_one_decimal(self):
        result = _ratio_str(1500)  # ratio = 16.0
        assert result == "16.0x"


# ---------------------------------------------------------------------------
# _func_label
# ---------------------------------------------------------------------------

class TestFuncLabel:
    def test_py_file_gives_module_colon_name(self):
        fs = make_fs(name="my_func", file="/path/to/mymod.py")
        label = _func_label(fs)
        assert label == "mymod:my_func"

    def test_py_file_same_as_main_file_gives_bare_name(self):
        fs = make_fs(name="my_func", file="/path/to/script.py")
        label = _func_label(fs, main_file="/path/to/script.py")
        assert label == "my_func"

    def test_c_callable_strips_redundant_module_prefix(self):
        # C callable: file = module name, name = "module.qualname"
        fs = make_fs(name="builtins.len", file="builtins")
        label = _func_label(fs)
        assert label == "builtins:len"

    def test_c_callable_without_prefix_passthrough(self):
        # name does NOT start with "module."
        fs = make_fs(name="completely_different", file="builtins")
        label = _func_label(fs)
        assert label == "builtins:completely_different"

    def test_frozen_module_file(self):
        fs = make_fs(name="importlib._bootstrap", file="<frozen importlib._bootstrap>")
        label = _func_label(fs)
        assert label == "<frozen importlib._bootstrap>:importlib._bootstrap"

    def test_no_file_returns_bare_name(self):
        fs = make_fs(name="my_func", file="")
        label = _func_label(fs)
        assert label == "my_func"

    def test_main_file_match_uses_relpath_equivalence(self, tmp_path):
        script = tmp_path / "script.py"
        script.write_text("pass")
        fs = make_fs(name="worker", file=str(script))
        label = _func_label(fs, main_file=str(script))
        assert label == "worker"

    def test_different_py_file_from_main_uses_module_prefix(self, tmp_path):
        main = tmp_path / "main.py"
        other = tmp_path / "helper.py"
        main.write_text("pass")
        other.write_text("pass")
        fs = make_fs(name="helper_fn", file=str(other))
        label = _func_label(fs, main_file=str(main))
        assert label == "helper:helper_fn"


# ---------------------------------------------------------------------------
# PlainFormatter.print_table — no baseline (no Delta column)
# ---------------------------------------------------------------------------

class TestPlainFormatterNoBaseline:
    def test_no_delta_column_in_output(self):
        fs = make_fs(name="target_func", call_times_ns=[1_000_000, 2_000_000])
        result = make_result(fs)
        output = capture_plain_table([result], baseline_idx=None)
        assert "Delta" not in output

    def test_function_name_appears(self):
        fs = make_fs(name="my_function", call_times_ns=[500_000])
        result = make_result(fs)
        output = capture_plain_table([result], baseline_idx=None)
        assert "my_function" in output

    def test_ncalls_appears(self):
        fs = make_fs(name="counted", ncalls=7, call_times_ns=[100_000] * 7)
        result = make_result(fs)
        output = capture_plain_table([result], baseline_idx=None)
        assert "7" in output

    def test_headers_present(self):
        fs = make_fs()
        result = make_result(fs)
        output = capture_plain_table([result], baseline_idx=None)
        assert "Function" in output
        assert "Calls" in output
        assert "Total" in output


# ---------------------------------------------------------------------------
# PlainFormatter.print_table — with baseline (Delta column present)
# ---------------------------------------------------------------------------

class TestPlainFormatterWithBaseline:
    def test_delta_column_present(self):
        fs_base = make_fs(name="baseline_fn", call_times_ns=[1_000_000])
        fs_new = make_fs(name="new_fn", call_times_ns=[2_000_000])
        results = [make_result(fs_base, "baseline"), make_result(fs_new, "new")]
        output = capture_plain_table(results, baseline_idx=0)
        assert "Delta" in output

    def test_baseline_row_shows_1x(self):
        fs_base = make_fs(name="baseline_fn", call_times_ns=[1_000_000])
        fs_new = make_fs(name="new_fn", call_times_ns=[2_000_000])
        results = [make_result(fs_base, "baseline"), make_result(fs_new, "new")]
        output = capture_plain_table(results, baseline_idx=0)
        assert "1x" in output

    def test_non_baseline_row_shows_ratio(self):
        # baseline: 1 ms mean, new: 2 ms mean → 2.00x
        fs_base = make_fs(name="base", call_times_ns=[1_000_000])
        fs_new = make_fs(name="newer", call_times_ns=[2_000_000])
        results = [make_result(fs_base, "base"), make_result(fs_new, "new")]
        output = capture_plain_table(results, baseline_idx=0)
        assert "2.00x" in output

    def test_baseline_dash_in_delta_time(self):
        fs_base = make_fs(name="base", call_times_ns=[1_000_000])
        fs_new = make_fs(name="new_fn", call_times_ns=[3_000_000])
        results = [make_result(fs_base, "base"), make_result(fs_new, "new")]
        output = capture_plain_table(results, baseline_idx=0)
        # baseline row has "—" in the Delta time column
        assert "—" in output
