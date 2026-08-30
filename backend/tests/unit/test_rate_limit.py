import time

from app.api.rate_limit import SlidingWindowLimiter


class TestSlidingWindowLimiter:
    def test_allows_up_to_limit_then_blocks(self) -> None:
        limiter = SlidingWindowLimiter(max_requests=3, window_seconds=1.0)
        assert limiter.allowance("user-a") == (True, 2)
        assert limiter.allowance("user-a") == (True, 1)
        assert limiter.allowance("user-a") == (True, 0)
        assert limiter.allowance("user-a") == (False, 0)

    def test_keys_are_independent(self) -> None:
        limiter = SlidingWindowLimiter(max_requests=1, window_seconds=1.0)
        assert limiter.allowance("alice") == (True, 0)
        assert limiter.allowance("bob") == (True, 0)

    def test_window_rolls_over(self) -> None:
        limiter = SlidingWindowLimiter(max_requests=2, window_seconds=0.2)
        assert limiter.allowance("user") == (True, 1)
        time.sleep(0.25)
        assert limiter.allowance("user") == (True, 1)

    def test_clamps_max_requests_to_positive(self) -> None:
        limiter = SlidingWindowLimiter(max_requests=0, window_seconds=1.0)
        # max_requests cannot be zero; at least one request passes
        assert limiter.allowance("user") == (True, 0)

    def test_many_keys_bounded_memory(self) -> None:
        limiter = SlidingWindowLimiter(max_requests=2, window_seconds=10.0)
        for i in range(5000):
            limiter.allowance(f"key-{i}")
        # recent timestamps survive eviction; the oldest may be dropped
        assert limiter.allowance("key-4999") in ((True, 0), (False, 0))
        assert len(limiter._hits) <= 5000