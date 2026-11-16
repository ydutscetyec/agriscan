"""The one clock the whole system uses.

Every stored timestamp is naive UTC. That was already true of the model defaults, but
several places compared those stored values against `datetime.now()`, which is local
time. On a UTC machine the two agree and nothing looks wrong; at UTC+8 every freshly
created row reads as eight hours old.

That is what expired every capture session seconds after it started, on a Philippine
laptop, while the whole test suite passed in a UTC container. One clock, used everywhere,
is the only way that class of bug stops happening.
"""

from __future__ import annotations

import datetime as dt


def utc_now() -> dt.datetime:
    """Naive UTC — the form every DATETIME column in this schema holds."""
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
