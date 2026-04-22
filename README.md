# step3: profit

A small, focused Python profiler built on `sys.monitoring` (Python 3.12+).

## Installation

```bash
uv tool install step3  # recommended
```

Or run without installing:

```bash
uvx --from step3 profit
```

Or with pip: `pip install step3`

## Usage

### CLI

Profile a script:

```bash
profit script.py
```

Focus on specific functions:

```bash
profit script.py -p mymod:func1 -p mymod:func2
```

Compare two functions side by side:

```bash
profit script.py -b mymod:func_old -p mymod:func_new
```

Run a module:

```bash
profit -m mypackage.module
```

Pass arguments to the script after `--`:

```bash
profit script.py -- --script-arg value
```

#### CLI options

| Flag | Description |
|------|-------------|
| `-p TARGET` | Function to show (repeatable) |
| `-b TARGET` | Baseline function for comparison |
| `-m MODULE` | Run a module as a script |
| `--sort` | Sort by `cumulative`, `tottime`, or `calls` (default: `cumulative`) |
| `--limit N` | Max functions to show (default: 20) |
| `--no-color` | Disable colored output |

Targets use importable names: `mymod:MyClass.method` or `mymod.func`.

### Python API

**Context manager** — profile a block of code:

```python
from step3 import profit

with profit as p:
    do_work()

p.print_stats()
```

**Decorator** — profile a specific function:

```python
from step3 import profit

@profit
def my_func():
    ...

my_func()
profit.print_stats()
```

## Requirements

- Python 3.12+
