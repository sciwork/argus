import re

from argus.timeutil import to_utc, utcnow_iso


def test_to_utc_with_positive_offset():
    assert to_utc("2026-04-18T14:00:54+08:00") == "2026-04-18T06:00:54"


def test_to_utc_strips_microseconds_and_offset():
    assert to_utc("2026-04-18T06:00:54.123456+00:00") == "2026-04-18T06:00:54"


def test_to_utc_z_suffix():
    assert to_utc("2026-04-18T06:00:54Z") == "2026-04-18T06:00:54"


def test_to_utc_none():
    assert to_utc(None) is None


def test_to_utc_empty_string():
    assert to_utc("") is None


def test_to_utc_naive_treated_as_utc():
    assert to_utc("2026-04-18T06:00:54") == "2026-04-18T06:00:54"


def test_utcnow_iso_format():
    result = utcnow_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", result)
