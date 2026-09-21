"""Quarterly scheduling guard, independent of delayed GitHub runner start times."""
from datetime import datetime
from zoneinfo import ZoneInfo


def quarter_key(moment):
    local = moment.astimezone(ZoneInfo('America/New_York'))
    return f'{local.year}-Q{(local.month - 1) // 3 + 1}'


def due(moment, last_successful_quarter=None, manual=False):
    if manual:
        return True
    local = moment.astimezone(ZoneInfo('America/New_York'))
    return (local.month in (1, 4, 7, 10) and local.day == 1 and local.hour >= 7
            and quarter_key(moment) != last_successful_quarter)
