"""
```python
"""
FILE PURPOSE
This file provides centralized date utility functions for the ZetaOps Copilot backend,
specifically for generating date ranges and filtering them to working days only. It was
introduced in the early v4 development to eliminate code duplication across scheduling
services, availability calculations, and reporting modules. This sits in the utils layer
of the architecture, providing pure functions with no database dependencies that can be
safely called from any service or business logic layer.

WHAT THIS FILE DOES — step by step
1. Imports Python's built-in date, timedelta, and typing modules for date manipulation
2. Defines date_range() function that generates all calendar dates between two dates
3. Defines working_days() function that filters a date range to only include specified weekdays
4. Uses a default Monday-through-Saturday work week pattern for manufacturing businesses
5. Returns lists of date objects that other services can iterate over for scheduling operations

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : date_range
Type         : function
Purpose      : Generates a complete list of consecutive calendar dates between a start and end 
               date (inclusive). This is used throughout the scheduling engine and availability 
               services when they need to iterate over every single day in a time period, 
               regardless of whether those days are working days or weekends.
Parameters   : start (date) - the first date to include in the range
               end (date) - the last date to include in the range
Returns      : List[date] containing every calendar date from start to end inclusive, in 
               ascending chronological order. Returns empty list if start > end.
Calls        : Python built-in timedelta() for day increment operations
DB/API       : None - this is a pure function with no external dependencies
Side effects : None - generates data in memory only, does not modify any external state

Name         : working_days
Type         : function
Purpose      : Filters a date range to return only dates that fall on specified working weekdays.
               This is the primary function used by the scheduling engine to determine which days
               jobs can be scheduled on, and by availability calculations to check when employees
               and machines are potentially available for work assignments.
Parameters   : start (date) - the first date to consider in the range
               end (date) - the last date to consider in the range  
               work_days (List[int], optional) - list of weekday integers where 0=Monday through 
               6=Sunday, defaults to [0,1,2,3,4,5] for Monday through Saturday
Returns      : List[date] containing only dates from the start-end range whose weekday() value
               appears in the work_days list. This gives callers exactly the dates when work
               can be scheduled according to the tenant's working day configuration.
Calls        : date_range() from this same file to get the full date range, then filters it
               date.weekday() method to determine which day of week each date represents
DB/API       : None - this is a pure function with no database or API dependencies
Side effects : None - performs filtering operations in memory only

WHO CALLS THIS FILE
- backend/app/services/availability_engine.py imports working_days() to calculate employee and machine availability windows
- backend/app/scheduler/engine.py imports both functions for job scheduling date calculations  
- backend/app/services/reporting_service.py imports date_range() for generating report date spans
- backend/app/routers/dashboard_router.py imports working_days() for productivity metrics over work periods
- backend/app/tasks/auto_advance.py imports working_days() to determine which days to process job advancement

IMPORTS EXPLAINED
- datetime.date: Python's built-in date class for representing calendar dates without time components, needed for all date arithmetic and comparisons in this utility
- datetime.timedelta: Python's built-in class for representing time durations, specifically used to increment dates by one day when building date ranges
- typing.List: Type hint for function return values to indicate these functions return lists of date objects, required for TypeScript strict mode compatibility

INTERN NOTES
- Easiest thing to break without realising: Changing the default work_days from [0,1,2,3,4,5] to include Sunday (6) will cause massive scheduling conflicts since most manufacturing tenants don't work Sundays but the engine will start scheduling jobs there
- Non-obvious design decision and why: The working_days function defaults to Monday-Saturday instead of Monday-Friday because most manufacturing businesses (printing, corrugated box, fabrication) in our target market operate on 6-day schedules to meet production demands
- Most common mistake when editing: Forgetting that date.weekday() returns 0 for Monday, not 1, so if you try to use 1-7 numbering instead of 0-6 you'll get completely wrong results with jobs scheduled on incorrect days
- Which design principle this file implements: Principle #1 (Engine computes, AI only narrates) - these are pure computational functions that the scheduling engine uses for date logic, with no AI involvement in the date calculations themselves
- What to check if this file behaves unexpectedly: Verify the start/end date parameters are actually Python date objects not strings or datetime objects, and confirm work_days parameter uses 0-6 weekday numbering not 1-7, and check that start <= end otherwise you get empty results
- If v5-whatsapp only: This file is shared between v4-dev and v5-whatsapp branches with no WhatsApp-specific functionality, so merging is straightforward with no special considerations needed
"""
```
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
