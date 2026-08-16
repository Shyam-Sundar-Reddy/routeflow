"""Fixture module for test_track_module.py — deliberately exercises every
case track_module() needs to tell apart: a function defined here, one
imported from elsewhere, one excluded by name, one already @track-ed by
hand, and a class (never touched — methods are out of scope for v1).
"""

from __future__ import annotations

from routeflow.tracing import track
from track_module_pkg.helpers import shared_helper  # imported, not defined here

__all__ = ["Foo", "already_tracked", "charge", "shared_helper", "validate"]


def validate(amount: int) -> bool:
    return amount > 0


def _internal_helper(x: int) -> int:
    return x + 1


def charge(amount: int) -> int:
    return shared_helper(amount)


@track
def already_tracked(x: int) -> int:
    return x


class Foo:
    def method(self) -> None:
        pass
