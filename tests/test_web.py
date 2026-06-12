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


def _client(per_minute=100, ask=None, run=None, translate=None, page="<h1>PAGE</h1>",
            convert=None, about_html="", og_png=b""):
    ask = ask or (lambda q: {"question": q, "mql": "SELECT x GO",
                             "result_count": 0, "results": []})
    run = run or (lambda mql: {"mql": mql, "result_count": 1, "results": []})
    translate = translate or (lambda q, refs=False: {"question": q, "mql": "SELECT t GO"})
    routes = make_routes(ask=ask, run=run, translate=translate, page_html=page,
                         limiter=RateLimiter(per_minute), convert=convert,
                         about_html=about_html, og_png=og_png)
    return TestClient(Starlette(routes=routes))


def test_api_translate_returns_mql_only():
    r = _client(translate=lambda q, refs=False: {"question": q, "mql": "SELECT z GO"}
                ).post("/api/translate", json={"question": "niphal verbs"})
    assert r.status_code == 200
    assert r.json()["mql"] == "SELECT z GO"
    assert "result_count" not in r.json()


def test_api_translate_requires_question():
    assert _client().post("/api/translate", json={}).status_code == 400


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


def test_api_run_returns_500_json_on_unexpected_error():
    def boom(mql):
        raise ValueError("kaboom")
    routes = make_routes(ask=lambda q: {}, run=boom, translate=lambda q, refs=False: {},
                         page_html="x", limiter=RateLimiter(100))
    c = TestClient(Starlette(routes=routes), raise_server_exceptions=False)
    r = c.post("/api/run", json={"mql": "Q GO"})
    assert r.status_code == 500
    assert "error" in r.json()


def test_api_ask_returns_500_json_on_unexpected_error():
    def boom(q):
        raise ValueError("kaboom")
    routes = make_routes(ask=boom, run=lambda m: {}, translate=lambda q, refs=False: {},
                         page_html="x", limiter=RateLimiter(100))
    c = TestClient(Starlette(routes=routes), raise_server_exceptions=False)
    r = c.post("/api/ask", json={"question": "x"})
    assert r.status_code == 500
    assert "error" in r.json()


def test_api_translate_passes_references_flag():
    seen = {}

    def tr(q, refs=False):
        seen["refs"] = refs
        return {"question": q, "mql": "SELECT z GO"}

    c = _client(translate=tr)
    c.post("/api/translate", json={"question": "x", "references": True})
    assert seen["refs"] is True
    c.post("/api/translate", json={"question": "x"})
    assert seen["refs"] is False


def test_api_convert_round_trip():
    client = _client(convert=lambda text: {"direction": "tf_to_mql",
                                           "output": "SELECT x GO",
                                           "notes": []})
    r = client.post("/api/convert", json={"text": "word sp=verb"})
    assert r.status_code == 200
    assert r.json()["direction"] == "tf_to_mql"


def test_api_convert_missing_text():
    client = _client(convert=lambda text: {})
    r = client.post("/api/convert", json={})
    assert r.status_code == 400


def test_api_convert_absent_when_not_wired():
    r = _client().post("/api/convert", json={"text": "x"})
    assert r.status_code == 404           # convert=None registers no route


def test_about_page_served():
    r = _client(about_html="<html><body>About me</body></html>").get("/about")
    assert r.status_code == 200
    assert "About me" in r.text


def test_og_image_served():
    r = _client(og_png=b"\x89PNG fake").get("/og.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content.startswith(b"\x89PNG")


def _page(name):
    from pathlib import Path
    return Path(__file__).resolve().parent.parent.joinpath(
        "demo", name).read_text(encoding="utf-8")


def test_main_page_has_seo_and_og_tags():
    html = _page("index.html")
    for needle in ('name="description"', 'rel="canonical"',
                   'property="og:title"', 'property="og:image"',
                   'name="twitter:card"', '"@type":"WebApplication"'):
        assert needle in html, needle


def test_about_page_has_seo_and_og_tags():
    html = _page("about.html")
    for needle in ('name="description"', 'rel="canonical"',
                   'property="og:title"', 'property="og:image"',
                   'name="twitter:card"'):
        assert needle in html, needle


def test_main_page_hero_and_two_box():
    html = _page("index.html")
    assert "with its Text-Fabric equivalent beside it" in html   # lede (exact)
    assert "Opus 4.8" not in html                       # stale model name gone
    assert "Text-Fabric equivalent" in html             # TF box label
    assert "derived by plain code" in html              # intro derivation clause


def test_examples_gallery_dual_language():
    html = _page("index.html")
    assert ">Examples<" in html
    assert "Worked examples" not in html
    assert '"tf": {"template"' in html   # showcase JSON carries tf (exact inlined form)
