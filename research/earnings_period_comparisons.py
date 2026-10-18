"""Comparable filed periods, including bounded 52/53-week fiscal calendars."""
from datetime import date


def family(period):
    if period[0] == 'instant':
        return 'instant'
    days = (date.fromisoformat(period[2]) - date.fromisoformat(period[1])).days + 1
    for name, lo, hi in [('quarter',70,105), ('half',150,200),
                         ('nine-month',250,290), ('annual',350,380)]:
        if lo <= days <= hi:
            return name
    return None


def year_ago(current, prior):
    """Both boundaries must match within one fiscal week plus leap-day drift.

    A matching duration family is mandatory. This never matches a YTD period to
    a quarter, nor an arbitrary nearby date to a previous-year period.
    """
    if current[0] != prior[0] or family(current) is None or family(current) != family(prior):
        return False
    for new, old in zip(current[1:], prior[1:]):
        a, b = date.fromisoformat(new), date.fromisoformat(old)
        if a.year != b.year + 1:
            return False
        try:
            anniversary = a.replace(year=b.year)
        except ValueError:  # February 29 in a non-leap prior year.
            anniversary = a.replace(year=b.year, day=28)
        if abs((anniversary - b).days) > 8:
            return False
    if current[0] == 'duration':
        lengths = [(date.fromisoformat(x[2]) - date.fromisoformat(x[1])).days for x in (current, prior)]
        if abs(lengths[0] - lengths[1]) > 8:
            return False
    return True
