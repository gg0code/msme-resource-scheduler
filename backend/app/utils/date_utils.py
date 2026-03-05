"""
utils/date_utils.py
-------------------
Shared date utility functions used across services and scripts.
Provides helpers to generate calendar ranges and filter to working days only,
avoiding duplication of date iteration logic throughout the codebase.
"""

from datetime import date, timedelta
from typing import List


def date_range(start: date, end: date) -> List[date]:
    """
    Return every calendar date from start to end, inclusive.

    Input  : start (date), end (date).
    Output : List[date] in ascending order. Returns empty list if start > end.
    """
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def working_days(start: date, end: date, work_days: List[int] = None) -> List[date]:
    """
    Return only the working days within a date range based on a configurable weekday mask.
    Defaults to Monday–Saturday (indices 0–5); Sunday (6) is excluded.

    Input  : start (date), end (date),
             work_days (list of weekday ints, 0=Monday … 6=Sunday; defaults to Mon–Sat).
    Output : List[date] containing only dates whose weekday is in the work_days mask.
    """
    if work_days is None:
        work_days = [0, 1, 2, 3, 4, 5]   # Monday through Saturday
    return [d for d in date_range(start, end) if d.weekday() in work_days]
