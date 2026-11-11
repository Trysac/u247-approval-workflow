"""Behavior tests for the public API of approval_workflow."""

from __future__ import annotations

import pytest

import approval_workflow


def test_normalize_trims_and_lowercases() -> None:
    assert approval_workflow.normalize("  Hello World ") == "hello world"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_normalize_rejects_blank_input(value: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        approval_workflow.normalize(value)


def test_version_is_semver() -> None:
    parts = approval_workflow.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
