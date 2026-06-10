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


def make_routes(ask, run, page_html: str, limiter: "RateLimiter") -> list:
    """Build the web demo's Starlette routes. `ask(question)->dict` and
    `run(mql)->dict` are the domain handlers; kept as params so this module
    has no dependency on server.py and the routes are testable in isolation."""
    from starlette.responses import HTMLResponse, JSONResponse
    from starlette.routing import Route

    async def _read_json(request) -> dict:
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - bad/empty body -> treat as {}
            return {}
        return body if isinstance(body, dict) else {}

    def _capped(request):
        return not limiter.allow(client_ip(request), monotonic())

    async def page(request):
        return HTMLResponse(page_html)

    async def ask_route(request):
        if _capped(request):
            return JSONResponse({"error": "rate limit exceeded; wait a moment"},
                                status_code=429)
        question = (await _read_json(request)).get("question", "").strip()
        if not question:
            return JSONResponse({"error": "missing 'question'"}, status_code=400)
        try:
            return JSONResponse(ask(question))
        except Exception:  # noqa: BLE001 - always answer in JSON, never a 500 HTML page
            return JSONResponse({"error": "internal error answering the question"},
                                status_code=500)

    async def run_route(request):
        if _capped(request):
            return JSONResponse({"error": "rate limit exceeded; wait a moment"},
                                status_code=429)
        mql = (await _read_json(request)).get("mql", "").strip()
        if not mql:
            return JSONResponse({"error": "missing 'mql'"}, status_code=400)
        try:
            return JSONResponse(run(mql))
        except Exception:  # noqa: BLE001 - always answer in JSON, never a 500 HTML page
            return JSONResponse({"error": "internal error running the query"},
                                status_code=500)

    return [
        Route("/", page, methods=["GET"]),
        Route("/api/ask", ask_route, methods=["POST"]),
        Route("/api/run", run_route, methods=["POST"]),
    ]


def register_web_routes(mcp, ask, run, page_html: str, limiter: "RateLimiter") -> None:
    """Attach the web routes to a FastMCP instance via its custom_route hook."""
    for route in make_routes(ask, run, page_html, limiter):
        mcp.custom_route(route.path, methods=list(route.methods))(route.endpoint)
