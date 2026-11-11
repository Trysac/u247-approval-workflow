# Stack

## Runtime

- Python >= 3.10.
- Standard library only: `dataclasses`, `datetime`, `decimal`, `re`, `collections`, `logging` and `typing`. No third-party runtime dependencies.

## Development

- Tests use pytest; the provided snapshot contains a pytest 9.2.0 compiled artifact for `tests/test_acceptance.py`.
- No other test, build, lint or type-check configuration is present in the provided snapshot.

## Discarded / not used

- No ORM or database driver: the engine is in-memory by design.
- No web framework: notifications and UI are explicitly out of scope.
- No workflow-state-machine or rules-engine dependency: the policy model is small and is the reason this library exists.
