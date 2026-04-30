"""Tests for the per-user throttle."""

from handlers.links import _stamps, _throttled


class TestThrottle:
    def setup_method(self):
        _stamps.clear()

    def test_first_ok(self):
        assert _throttled(100) is False

    def test_limit_reached(self):
        for _ in range(10):
            _throttled(200)
        assert _throttled(200) is True

    def test_users_independent(self):
        for _ in range(10):
            _throttled(300)
        assert _throttled(301) is False
