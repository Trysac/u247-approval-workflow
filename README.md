# approval-workflow

[![PyPI version](https://img.shields.io/pypi/v/trysac-approval-workflow)](https://pypi.org/project/trysac-approval-workflow/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-approval-workflow)](LICENSE)
[![CI](https://github.com/Trysac/u247-approval-workflow/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u247-approval-workflow/actions/workflows/ci.yml)

Multi-level approval engine: amount-based routing, sequential levels with quorums, separation of duties, time-bound delegation, escalation on timeout and terminal states

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-approval-workflow
# or
uv add trysac-approval-workflow
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import approval_workflow

# normalize() trims surrounding whitespace and lower-cases the text.
print(approval_workflow.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    approval_workflow.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
