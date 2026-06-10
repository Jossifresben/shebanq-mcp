"""HTTP layer for the live web demo: a per-IP rate cap, client-IP extraction,
and the browser-facing routes. Kept separate from server.py so the domain
handlers (ask/run) stay there and this module owns only HTTP concerns."""
import threading


class RateLimiter:
    """Per-IP token bucket. `per_minute` tokens, refilled continuously. Pass
    `now` (a monotonic seconds float) explicitly so it is testable."""

    def __init__(self, per_minute: int):
        self._capacity = float(per_minute)
        self._rate = per_minute / 60.0          # tokens per second
        self._buckets: dict[str, tuple[float, float]] = {}  # ip -> (tokens, ts)
        self._lock = threading.Lock()

    def allow(self, ip: str, now: float) -> bool:
        with self._lock:
            tokens, ts = self._buckets.get(ip, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - ts) * self._rate)
            if tokens < 1.0:
                self._buckets[ip] = (tokens, now)
                return False
            self._buckets[ip] = (tokens - 1.0, now)
            return True


def client_ip(request) -> str:
    """Real client IP. Behind Render's TLS proxy the socket peer is the proxy,
    so prefer the first hop in X-Forwarded-For."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", "unknown") if client else "unknown"


from time import monotonic  # noqa: E402 - intentional mid-file import


def make_routes(ask, run, translate, page_html: str, limiter: "RateLimiter") -> list:
    """Build the web demo's Starlette routes. `ask(question)`, `translate(question)`
    and `run(mql)` are the domain handlers — kept as params so this module has no
    dependency on server.py and the routes are testable in isolation. `ask`
    translates+runs in one shot; `translate` only generates the MQL; `run`
    executes a supplied MQL."""
    from starlette.responses import HTMLResponse, JSONResponse
    from starlette.routing import Route

    async def _read_json(request) -> dict:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - bad/empty body -> treat as {}
            return {}
        return body if isinstance(body, dict) else {}

    def _post_route(handler, key: str, op: str):
        """A rate-capped POST route that reads `key` from the JSON body, calls
        `handler(value)`, and always answers in JSON (never a 500 HTML page)."""
        async def route(request):
            if not limiter.allow(client_ip(request), monotonic()):
                return JSONResponse({"error": "rate limit exceeded; wait a moment"},
                                    status_code=429)
            value = (await _read_json(request)).get(key, "").strip()
            if not value:
                return JSONResponse({"error": f"missing '{key}'"}, status_code=400)
            try:
                return JSONResponse(handler(value))
            except Exception:  # noqa: BLE001 - never leak a traceback as 500 HTML
                return JSONResponse({"error": f"internal error {op}"}, status_code=500)
        return route

    async def page(request):
        return HTMLResponse(page_html)

    async def translate_route(request):
        if not limiter.allow(client_ip(request), monotonic()):
            return JSONResponse({"error": "rate limit exceeded; wait a moment"},
                                status_code=429)
        body = await _read_json(request)
        question = (body.get("question") or "").strip()
        if not question:
            return JSONResponse({"error": "missing 'question'"}, status_code=400)
        try:
            return JSONResponse(translate(question, bool(body.get("references"))))
        except Exception:  # noqa: BLE001 - never leak a traceback as 500 HTML
            return JSONResponse({"error": "internal error translating the question"},
                                status_code=500)

    return [
        Route("/", page, methods=["GET"]),
        Route("/api/translate", translate_route, methods=["POST"]),
        Route("/api/ask", _post_route(ask, "question",
              "answering the question"), methods=["POST"]),
        Route("/api/run", _post_route(run, "mql",
              "running the query"), methods=["POST"]),
    ]


def register_web_routes(mcp, ask, run, translate, page_html: str,
                        limiter: "RateLimiter") -> None:
    """Attach the web routes to a FastMCP instance via its custom_route hook."""
    for route in make_routes(ask, run, translate, page_html, limiter):
        mcp.custom_route(route.path, methods=list(route.methods))(route.endpoint)
