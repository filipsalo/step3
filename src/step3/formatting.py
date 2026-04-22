from __future__ import annotations

import os
import sys
from math import floor, log10
from typing import Optional

from .results import FuncStats, StatsResult, _pct

# ANSI color codes
_RESET = "\033[0m"
_BOLD = "\033[1m"
_GREEN = "\033[92m"
_RED = "\033[91m"
_DIM = "\033[2m"
_YELLOW = "\033[93m"

# Per-column base colors — green/red reserved for delta comparison
_COL_COLORS = {
    "total":  _YELLOW,
}

_KEYS    = ["func", "calls", "total", "min", "max", "mean", "stddev", "delta_t", "delta_x"]
_HEADERS = ["Function", "Calls", "Total", "Min", "Max", "Mean", "± σ", "Delta", ""]


def _use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _fmt_time(seconds: float) -> str:
    """Auto-scale seconds to a human-readable string with integer values."""
    if seconds == 0:
        return "0 s"
    abs_s = abs(seconds)
    if abs_s >= 1:
        return f"{round(seconds)} s"
    if abs_s >= 1e-3:
        return f"{round(seconds * 1e3)} ms"
    if abs_s >= 1e-6:
        return f"{round(seconds * 1e6)} μs"
    return f"{round(seconds * 1e9)} ns"


def _fmt_time_opt(seconds: Optional[float]) -> str:
    return "—" if seconds is None else _fmt_time(seconds)


def _colorize(text: str, color: str, use_color: bool) -> str:
    return f"{color}{text}{_RESET}" if use_color else text


def _ratio_str(pct: Optional[float]) -> str:
    """Convert a percent change to a multiplier string like '1.20x' or '0.0014x'."""
    if pct is None:
        return ""
    ratio = 1 + pct / 100
    if ratio >= 100:
        return f"{ratio:.0f}x"
    if ratio >= 10:
        return f"{ratio:.1f}x"
    if ratio >= 0.001:
        return f"{ratio:.2f}x"
    # Very small ratios: show enough decimals to have 2 significant figures
    mag = floor(log10(ratio))  # e.g. -4 for 0.00014
    decimals = -mag + 1
    return f"{ratio:.{decimals}f}x"


def _func_label(fs: FuncStats, main_file: Optional[str] = None) -> str:
    if not fs.file:
        return fs.name
    f = fs.file
    if main_file and f.endswith(".py") and os.path.abspath(f) == os.path.abspath(main_file):
        return fs.name  # bare qualname — it's in the main script
    if f.endswith(".py"):
        mod = os.path.basename(f)[:-3]
        return f"{mod}:{fs.name}"
    elif f.startswith("<"):
        return f"{f}:{fs.name}"
    else:
        # C callable: fs.file is module name, fs.name is "module.qualname"
        prefix = f + "."
        name = fs.name[len(prefix):] if fs.name.startswith(prefix) else fs.name
        return f"{f}:{name}"


def _ratio_color(pct: Optional[float]) -> str:
    if pct is None or pct == 0:
        return ""
    return _GREEN if pct < 0 else _RED



def _col_widths(rows: list[list[str]]) -> list[int]:
    """Compute minimum column widths to fit all values."""
    if not rows:
        return []
    ncols = len(rows[0])
    return [max(len(row[col]) for row in rows) for col in range(ncols)]


def _row_vals(fs: FuncStats, mean_delta_s: Optional[float] = None, mean_pct: Optional[float] = None, main_file: Optional[str] = None, is_baseline: bool = False) -> list[str]:
    if is_baseline:
        delta_t, delta_x = "—", "1x"
    elif mean_delta_s is not None and mean_pct is not None:
        delta_t, delta_x = _fmt_time(mean_delta_s), _ratio_str(mean_pct)
    else:
        delta_t, delta_x = "—", "—"
    return [
        _func_label(fs, main_file),
        str(fs.ncalls),
        _fmt_time(fs.cumtime),
        _fmt_time_opt(fs.min_time),
        _fmt_time_opt(fs.max_time),
        _fmt_time_opt(fs.mean_time),
        f"± {_fmt_time(fs.stddev_time)}" if fs.stddev_time is not None else "—",
        delta_t,
        delta_x,
    ]


class PlainFormatter:
    """Terminal formatter using plain ANSI codes. No external dependencies."""

    def __init__(self):
        self._color = _use_color()

    def _render_row(
        self,
        row: list[str],
        widths: list[int],
        keys: list[str],
        mean_pct: Optional[float] = None,
        is_header: bool = False,
        is_baseline: bool = False,
    ) -> str:
        parts = []
        for i, (key, val) in enumerate(zip(keys, row)):
            w = widths[i]
            if key == "func":
                cell = val.ljust(w)
                if self._color and is_header:
                    cell = f"{_BOLD}{cell}{_RESET}"
                elif self._color and is_baseline:
                    cell = f"{_DIM}{cell}{_RESET}"
                elif self._color and mean_pct is not None:
                    cell = f"{_ratio_color(mean_pct)}{cell}{_RESET}"
            elif key in ("delta_t", "delta_x"):
                cell = val.center(w) if val == "—" else (val.rjust(w) if key == "delta_t" else val.ljust(w))
                if self._color and is_header:
                    cell = f"{_BOLD}{cell}{_RESET}"
                elif self._color and is_baseline:
                    cell = f"{_DIM}{cell}{_RESET}"
                elif self._color and mean_pct is not None:
                    cell = f"{_ratio_color(mean_pct)}{cell}{_RESET}"
            elif key == "stddev":
                cell = val.ljust(w)
                if self._color and is_header:
                    cell = f"{_BOLD}{cell}{_RESET}"
            else:
                color = _COL_COLORS.get(key, "")
                cell = val.center(w) if val == "—" else val.rjust(w)
                if self._color and is_header:
                    cell = f"{_BOLD}{cell}{_RESET}"
                elif self._color and color:
                    cell = f"{color}{cell}{_RESET}"
            parts.append(cell)
        return "  ".join(parts)

    def print_stats(self, result: StatsResult, title: Optional[str] = None, main_file: Optional[str] = None) -> None:
        keys    = _KEYS[:-2]
        headers = _HEADERS[:-2]

        rows = [_row_vals(fs, None, None, main_file) for fs in result.func_stats]
        rows = [r[:-2] for r in rows]
        if not rows:
            return

        widths = _col_widths([headers] + rows)

        lbl = title or result.target_name
        header = f"  {lbl}  {_fmt_time(result.total_time)}".rstrip() if lbl else ""
        print()
        if header:
            print(_colorize(header, _BOLD, self._color))
        print(self._render_row(headers, widths, keys, is_header=True))
        for row in rows:
            print(self._render_row(row, widths, keys))

    def print_table(
        self,
        results: list[StatsResult],
        baseline_idx: Optional[int] = None,
        title: Optional[str] = None,
        main_file: Optional[str] = None,
    ) -> None:
        inline_baseline_fs = None
        if baseline_idx is not None and results[baseline_idx].func_stats:
            inline_baseline_fs = results[baseline_idx].func_stats[0]

        entries: list[tuple[StatsResult, Optional[float], Optional[float], bool]] = []
        for i, r in enumerate(results):
            if not r.func_stats:
                continue
            fs = r.func_stats[0]
            is_baseline_row = (baseline_idx is not None and i == baseline_idx)
            if inline_baseline_fs and not is_baseline_row:
                ref = inline_baseline_fs
                mean_pct = _pct(fs.mean_time, ref.mean_time)
                mean_delta_s = (fs.mean_time - ref.mean_time) if (fs.mean_time is not None and ref.mean_time is not None) else None
            else:
                mean_pct = None
                mean_delta_s = None
            entries.append((r, mean_delta_s, mean_pct, is_baseline_row))

        show_delta = baseline_idx is not None
        keys    = _KEYS    if show_delta else _KEYS[:-2]
        headers = _HEADERS if show_delta else _HEADERS[:-2]

        rows = [_row_vals(r.func_stats[0], d_s, pct, main_file, is_bl) for r, d_s, pct, is_bl in entries]
        if not show_delta:
            rows = [r[:-2] for r in rows]
        if not rows:
            return

        widths = _col_widths([headers] + rows)

        label = title or (results[0].target_name if len(results) == 1 else "")
        total_s = _fmt_time(results[0].total_time) if len(results) == 1 else ""
        header = f"  {label}  {total_s}".rstrip() if label else ""
        print()
        if header:
            print(_colorize(header, _BOLD, self._color))
        print(self._render_row(headers, widths, keys, is_header=True))

        for (r, d_s, mean_pct, is_bl), row in zip(entries, rows):
            print(self._render_row(row, widths, keys, mean_pct, is_baseline=is_bl))


def get_formatter() -> PlainFormatter:
    return PlainFormatter()
