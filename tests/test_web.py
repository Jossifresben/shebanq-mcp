from shebanq_mcp.web import RateLimiter, client_ip


def test_rate_limiter_allows_up_to_limit_then_blocks():
    rl = RateLimiter(per_minute=3)
    assert rl.allow("1.1.1.1", now=1000.0)
    assert rl.allow("1.1.1.1", now=1000.0)
    assert rl.allow("1.1.1.1", now=1000.0)
    assert not rl.allow("1.1.1.1", now=1000.0)   # 4th in the same instant


def test_rate_limiter_refills_over_time():
    rl = RateLimiter(per_minute=60)              # 1 token/sec
    for _ in range(60):
        assert rl.allow("ip", now=0.0)
    assert not rl.allow("ip", now=0.0)
    assert rl.allow("ip", now=1.01)              # ~1 token refilled after 1s


def test_rate_limiter_is_per_ip():
    rl = RateLimiter(per_minute=1)
    assert rl.allow("a", now=0.0)
    assert not rl.allow("a", now=0.0)
    assert rl.allow("b", now=0.0)                # different IP unaffected


class _Req:
    def __init__(self, headers, client_host="9.9.9.9"):
        self.headers = headers

        class _C:
            host = client_host
        self.client = _C()


def test_client_ip_prefers_x_forwarded_for():
    req = _Req({"x-forwarded-for": "203.0.113.5, 70.41.3.18"})
    assert client_ip(req) == "203.0.113.5"


def test_client_ip_falls_back_to_peer():
    req = _Req({})
    assert client_ip(req) == "9.9.9.9"
