"""Excel's date serial numbers (the 1900 date system).

Day 1 is 1 January 1900. Excel counts a 29 February 1900 that never was
(serial 60), kept for Lotus 1-2-3; every serial from 61 on is one more than
the true day count, and the same is done here so files agree with Excel.
"""
from __future__ import annotations

import datetime as _dt

_EPOCH = _dt.date(1899, 12, 31)


def serial_from_date(d: _dt.date) -> float:
    n = (d - _EPOCH).days
    if n >= 60:
        n += 1
    return float(n)


def date_from_serial(serial: float) -> _dt.date:
    n = int(serial // 1)
    if n < 0 or n > 2958465:
        raise ValueError("date out of range")
    if n == 60:
        return _dt.date(1900, 2, 28)    # the day that never was; shown as 29 Feb by the formatter
    if n > 60:
        n -= 1
    return _EPOCH + _dt.timedelta(days=n)


def datetime_from_serial(serial: float) -> _dt.datetime:
    d = date_from_serial(serial)
    seconds = round((serial - int(serial // 1)) * 86400, 3)
    if seconds >= 86400:
        seconds = 86400 - 0.001
    return _dt.datetime(d.year, d.month, d.day) + _dt.timedelta(seconds=seconds)


def serial_from_datetime(t: _dt.datetime) -> float:
    return serial_from_date(t.date()) + (t.hour * 3600 + t.minute * 60 + t.second
                                         + t.microsecond / 1e6) / 86400.0


def is_leap_bug(serial: float) -> bool:
    return int(serial // 1) == 60
