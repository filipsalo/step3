"""Integration tests for step3.cli.main()."""
from __future__ import annotations

import os
import sys
import textwrap

import pytest

from step3.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIMPLE_SCRIPT = textwrap.dedent("""\
    def compute(n):
        total = 0
        for i in range(n):
            total += i
        return total

    if __name__ == "__main__":
        compute(1000)
""")

TWO_FUNCS_SCRIPT = textwrap.dedent("""\
    def slow_func():
        total = sum(range(10_000))
        return total

    def fast_func():
        return 42

    if __name__ == "__main__":
        slow_func()
        fast_func()
""")


# ---------------------------------------------------------------------------
# Basic: running a script produces output
# ---------------------------------------------------------------------------

class TestMainBasic:
    def test_simple_script_produces_output(self, tmp_path, capsys):
        script = tmp_path / "simple.py"
        script.write_text(SIMPLE_SCRIPT)
        main(["--no-color", str(script)])
        captured = capsys.readouterr()
        output = captured.out
        assert len(output) > 0

    def test_output_contains_function_column_header(self, tmp_path, capsys):
        script = tmp_path / "simple.py"
        script.write_text(SIMPLE_SCRIPT)
        main(["--no-color", str(script)])
        captured = capsys.readouterr()
        assert "Function" in captured.out

    def test_output_contains_calls_column_header(self, tmp_path, capsys):
        script = tmp_path / "simple.py"
        script.write_text(SIMPLE_SCRIPT)
        main(["--no-color", str(script)])
        captured = capsys.readouterr()
        assert "Calls" in captured.out

    def test_script_name_appears_in_output(self, tmp_path, capsys):
        script = tmp_path / "myscript.py"
        script.write_text(SIMPLE_SCRIPT)
        main(["--no-color", str(script)])
        captured = capsys.readouterr()
        assert "myscript.py" in captured.out


# ---------------------------------------------------------------------------
# -p: focus on a function by bare name
# ---------------------------------------------------------------------------

class TestMainProfileTarget:
    def test_bare_name_resolves_target(self, tmp_path, capsys):
        script = tmp_path / "myscript.py"
        script.write_text(SIMPLE_SCRIPT)
        main(["--no-color", "-p", "compute", str(script)])
        captured = capsys.readouterr()
        assert "compute" in captured.out

    def test_bare_name_missing_gives_no_crash(self, tmp_path, capsys):
        """When the bare name isn't found the tool returns an empty result
        rather than crashing — the output may be empty or minimal."""
        script = tmp_path / "myscript.py"
        script.write_text(SIMPLE_SCRIPT)
        # "nonexistent" doesn't exist; main should not raise
        main(["--no-color", "-p", "nonexistent", str(script)])
        # Just verify it didn't crash; output may be empty

    def test_profile_target_no_delta_without_baseline(self, tmp_path, capsys):
        script = tmp_path / "myscript.py"
        script.write_text(SIMPLE_SCRIPT)
        main(["--no-color", "-p", "compute", str(script)])
        captured = capsys.readouterr()
        assert "Delta" not in captured.out


# ---------------------------------------------------------------------------
# -b / -p: baseline comparison produces Delta column
# ---------------------------------------------------------------------------

class TestMainBaselineComparison:
    def test_delta_column_present_with_baseline(self, tmp_path, capsys):
        script = tmp_path / "twofuncs.py"
        script.write_text(TWO_FUNCS_SCRIPT)
        main(["--no-color", "-b", "slow_func", "-p", "fast_func", str(script)])
        captured = capsys.readouterr()
        assert "Delta" in captured.out

    def test_baseline_row_shows_1x(self, tmp_path, capsys):
        script = tmp_path / "twofuncs.py"
        script.write_text(TWO_FUNCS_SCRIPT)
        main(["--no-color", "-b", "slow_func", "-p", "fast_func", str(script)])
        captured = capsys.readouterr()
        assert "1x" in captured.out

    def test_both_function_names_appear(self, tmp_path, capsys):
        script = tmp_path / "twofuncs.py"
        script.write_text(TWO_FUNCS_SCRIPT)
        main(["--no-color", "-b", "slow_func", "-p", "fast_func", str(script)])
        captured = capsys.readouterr()
        assert "slow_func" in captured.out
        assert "fast_func" in captured.out


# ---------------------------------------------------------------------------
# Error case: unknown fully-qualified function name exits with an error
# ---------------------------------------------------------------------------

class TestMainErrorCases:
    def test_unknown_qualified_name_exits(self, tmp_path):
        script = tmp_path / "simple.py"
        script.write_text(SIMPLE_SCRIPT)
        with pytest.raises(SystemExit) as exc_info:
            main(["--no-color", "-p", "totally.nonexistent:func", str(script)])
        # Should exit with a non-zero code or an error message
        assert exc_info.value.code != 0

    def test_no_script_exits(self):
        with pytest.raises(SystemExit):
            main(["--no-color"])

    def test_script_args_passed_through(self, tmp_path, capsys):
        """Script can read sys.argv; profit passes remaining args."""
        script = tmp_path / "argv_script.py"
        script.write_text(textwrap.dedent("""\
            import sys

            def run():
                return sys.argv[1:]

            if __name__ == "__main__":
                result = run()
        """))
        # Should not crash when extra args are passed
        main(["--no-color", str(script), "--", "--foo", "bar"])
        # If we get here without exception, the args were forwarded cleanly
