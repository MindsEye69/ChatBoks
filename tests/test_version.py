"""Tests for Git-derived ChatBoks development versions."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from version import android_version_code, format_development_version, version_for_commit_distance


@pytest.mark.parametrize(
    ("build_number", "expected"),
    [
        (0, "0.1.00"),
        (1, "0.1.01"),
        (99, "0.1.99"),
        (100, "0.2.00"),
        (199, "0.2.99"),
    ],
)
def test_development_version_rollover(build_number: int, expected: str) -> None:
    assert format_development_version(build_number) == expected


def test_current_version_commit_is_the_0_1_00_anchor_build() -> None:
    assert version_for_commit_distance(1) == "0.1.00"
    assert version_for_commit_distance(2) == "0.1.01"


def test_negative_build_numbers_are_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        format_development_version(-1)


@pytest.mark.parametrize(
    ("version", "expected"),
    [("0.1.00", 100), ("0.1.99", 199), ("0.2.00", 200), ("1.0.00", 10_000)],
)
def test_android_version_code_matches_public_version(version: str, expected: int) -> None:
    assert android_version_code(version) == expected


def test_android_version_code_rejects_unformatted_versions() -> None:
    with pytest.raises(ValueError, match="major.minor.build"):
        android_version_code("1.0")
