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
