"""Bounded reception limits (v0.15.1): every env-tunable cap is clamped.

The reception layer documents its caps as "env-tunable but always
bounded". These tests hold that claim against hostile environment
values — unset, non-integer garbage, negative, zero, absurdly large —
for EVERY limit, and hold the upload concurrency gate to the same
discipline. Before v0.15.1 the limits parsed raw integers with no
minimum or maximum, so "always bounded" was a description, not a fact.
"""
import pytest

from geologia.api import upload_concurrency
from geologia.data_layer import reception

LIMIT_CASES = [
    (reception.max_upload_bytes, "GEOLOGIA_MAX_UPLOAD_BYTES",
     reception.DEFAULT_MAX_UPLOAD_BYTES, 1, 1 << 30),
    (reception.max_archive_ratio, "GEOLOGIA_MAX_ARCHIVE_RATIO",
     reception.DEFAULT_MAX_ARCHIVE_RATIO, 2, 10_000),
    (reception.max_archive_entries, "GEOLOGIA_MAX_ARCHIVE_ENTRIES",
     reception.DEFAULT_MAX_ARCHIVE_ENTRIES, 1, 4096),
    (reception.max_archive_uncompressed, "GEOLOGIA_MAX_ARCHIVE_UNCOMPRESSED",
     reception.DEFAULT_MAX_ARCHIVE_UNCOMPRESSED, 1 << 20, 1 << 33),
    (reception.max_line_bytes, "GEOLOGIA_MAX_LINE_BYTES",
     reception.DEFAULT_MAX_LINE_BYTES, 256, 1 << 24),
]


@pytest.mark.parametrize(
    "getter,name,default,minimum,maximum", LIMIT_CASES)
def test_limit_getter_is_always_bounded(getter, name, default, minimum,
                                        maximum, monkeypatch):
    # unset -> the documented default
    monkeypatch.delenv(name, raising=False)
    assert getter() == default

    # non-integer garbage -> the documented default, never a crash
    monkeypatch.setenv(name, "not-a-number")
    assert getter() == default
    monkeypatch.setenv(name, "10; rm -rf /")
    assert getter() == default

    # negative and zero -> clamped to the hard minimum
    for hostile in ("-5", "0", "-999999999"):
        monkeypatch.setenv(name, hostile)
        assert getter() == minimum

    # absurdly large -> clamped to the hard maximum
    monkeypatch.setenv(name, str(1 << 100))
    assert getter() == maximum

    # a mid-range value passes through untouched
    mid = minimum + (maximum - minimum) // 2
    monkeypatch.setenv(name, str(mid))
    assert getter() == mid

    # exactly the bounds pass through untouched
    monkeypatch.setenv(name, str(minimum))
    assert getter() == minimum
    monkeypatch.setenv(name, str(maximum))
    assert getter() == maximum


def test_upload_concurrency_is_bounded(monkeypatch):
    monkeypatch.delenv("GEOLOGIA_UPLOAD_CONCURRENCY", raising=False)
    assert upload_concurrency() == 4  # documented default

    monkeypatch.setenv("GEOLOGIA_UPLOAD_CONCURRENCY", "garbage")
    assert upload_concurrency() == 4

    for hostile in ("-3", "0"):
        monkeypatch.setenv("GEOLOGIA_UPLOAD_CONCURRENCY", hostile)
        assert upload_concurrency() == 1

    monkeypatch.setenv("GEOLOGIA_UPLOAD_CONCURRENCY", "9999")
    assert upload_concurrency() == 64

    monkeypatch.setenv("GEOLOGIA_UPLOAD_CONCURRENCY", "2")
    assert upload_concurrency() == 2
