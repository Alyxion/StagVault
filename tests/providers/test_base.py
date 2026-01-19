"""Tests for base provider classes and rate limiting."""

from __future__ import annotations

import pytest

from stagvault.providers.base import RateLimitInfo


class TestRateLimitInfo:
    """Tests for rate limit tracking."""

    def test_from_headers(self):
        headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "50",
            "X-RateLimit-Reset": "30"
        }
        info = RateLimitInfo.from_headers(headers)

        assert info.limit == 100
        assert info.remaining == 50
        assert info.reset_seconds == 30

    def test_is_exhausted(self):
        info = RateLimitInfo(limit=100, remaining=0)
        assert info.is_exhausted is True

        info = RateLimitInfo(limit=100, remaining=1)
        assert info.is_exhausted is False

    def test_should_wait(self):
        # For limit=100, buffer is 5% = 5
        info = RateLimitInfo(limit=100, remaining=4)
        assert info.should_wait is True

        info = RateLimitInfo(limit=100, remaining=10)
        assert info.should_wait is False

    def test_dynamic_buffer(self):
        # Low limit (< 100): 10% buffer
        info = RateLimitInfo(limit=50, remaining=50)
        assert info.buffer == 5

        # Medium limit (100-500): 5% buffer
        info = RateLimitInfo(limit=200, remaining=200)
        assert info.buffer == 10

        # High limit (> 500): 3% buffer
        info = RateLimitInfo(limit=1000, remaining=1000)
        assert info.buffer == 30

        # Very low limit: minimum buffer of 3
        info = RateLimitInfo(limit=10, remaining=10)
        assert info.buffer == 3

    def test_is_critical(self):
        info = RateLimitInfo(limit=100, remaining=5)
        assert info.is_critical is True

        info = RateLimitInfo(limit=100, remaining=15)
        assert info.is_critical is False

    def test_wait_time(self):
        info = RateLimitInfo(limit=100, remaining=0, reset_seconds=60)

        wait = info.wait_time()
        assert 59 <= wait <= 60
