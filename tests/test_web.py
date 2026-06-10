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


from starlette.applications import Starlette
from starlette.testclient import TestClient

from shebanq_mcp.web import make_routes, RateLimiter


def _client(per_minute=100, ask=None, run=None, page="<h1>PAGE</h1>"):
    ask = ask or (lambda q: {"question": q, "mql": "SELECT x GO",
                             "result_count": 0, "results": []})
    run = run or (lambda mql: {"mql": mql, "result_count": 1, "results": []})
    routes = make_routes(ask=ask, run=run, page_html=page,
                         limiter=RateLimiter(per_minute))
    return TestClient(Starlette(routes=routes))


def test_get_root_serves_page():
    r = _client().get("/")
    assert r.status_code == 200
    assert "PAGE" in r.text


def test_api_ask_returns_result_json():
    r = _client().post("/api/ask", json={"question": "niphal verbs"})
    assert r.status_code == 200
    assert r.json()["mql"] == "SELECT x GO"


def test_api_ask_requires_question():
    r = _client().post("/api/ask", json={})
    assert r.status_code == 400


def test_api_run_runs_supplied_mql():
    r = _client(run=lambda mql: {"mql": mql, "result_count": 48, "results": []}
                ).post("/api/run", json={"mql": "SELECT ALL OBJECTS WHERE [word] GO"})
    assert r.status_code == 200
    assert r.json()["result_count"] == 48


def test_api_run_requires_mql():
    assert _client().post("/api/run", json={}).status_code == 400


def test_rate_cap_returns_429():
    c = _client(per_minute=2)
    assert c.post("/api/run", json={"mql": "Q GO"}).status_code == 200
    assert c.post("/api/run", json={"mql": "Q GO"}).status_code == 200
    assert c.post("/api/run", json={"mql": "Q GO"}).status_code == 429
