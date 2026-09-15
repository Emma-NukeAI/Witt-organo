"""
net_throttle — process-level per-host rate limiter for the outbound HTTP the pipeline makes (ADR-0078).

WHY THIS MODULE EXISTS: the query service runs WITT_RUN_WORKERS threads (default 2) inside ONE uvicorn
process (`--workers 1` is REQUIRED by the Dockerfile — in-process caches and the serialized write queue
assume a single process; ADR-0048). Every worker that fires Path B hits NCBI E-utilities and Europe PMC
with no pacing at all, and NCBI answers `X-RateLimit-Limit: 3` per second without an API key. Two workers
racing the same host is exactly how a run collects HTTP 429s that then look like "no results" downstream.

Because the workers are THREADS of the same process, a `threading.Lock` + `time.monotonic` registry keyed
by host is the whole solution: one Throttle per host, shared by every caller in the process. No file
locks, no external broker. If the service ever moves to several processes the lock stops covering them —
that is a documented boundary of this design, not a hidden assumption.

WHAT IT DOES (stdlib-pure — a workspace tool must stay stdlib-pure, CLAUDE.md §6 Layer 0):
  Throttle(host, min_interval_s).wait()   blocks until at least `min_interval_s` elapsed since the previous
                                          admitted call for that host; returns the seconds it actually slept
                                          (a MEASUREMENT, so callers can declare it in the ledger).
  get_throttle(host, min_interval_s)      process-global registry; the same host always returns the same
                                          Throttle object. Passing an interval UPDATES the shared object
                                          (the interval is derived from env at call time — key present or
                                          not — so the last caller's derivation wins; they all derive the
                                          same value from the same env).
  retry_once_on_429(fn, stats=None)       runs fn(); on urllib HTTPError 429 waits `Retry-After` seconds
                                          (or DEFAULT_RETRY_WAIT_S = 1.0 when the header is absent or is
                                          an HTTP-date) and runs fn() ONCE more. A second 429 propagates:
                                          the caller declares status 'error' in its ledger row and the run
                                          continues (§6 no-hang). Never a loop.

Nothing here retries silently more than once, nothing swallows an error, nothing re-executes on its own.
"""
import threading
import time
import urllib.error

DEFAULT_RETRY_WAIT_S = 1.0     # ADR-0078: espera cuando 429 llega sin Retry-After utilizable
MAX_RETRY_AFTER_S = 60.0       # techo: un Retry-After absurdo no cuelga un worker (§6 no-hang)

# Indirection so a smoke can stub sleeping without patching `time` for the whole process.
_sleep = time.sleep
_monotonic = time.monotonic


class Throttle:
    """Per-host pacing. Thread-safe; one instance is meant to be shared by every thread in the process."""

    def __init__(self, host, min_interval_s):
        self.host = host
        self.min_interval_s = float(min_interval_s)
        self._lock = threading.Lock()
        self._last_admitted = None  # monotonic timestamp of the previous admitted call (None = never)

    def set_min_interval(self, min_interval_s):
        self.min_interval_s = float(min_interval_s)  # float assignment is atomic; no lock needed

    def wait(self):
        """Block until this host admits another call. Returns seconds actually waited (measurement).

        The lock is HELD while pacing: waiters for the same host queue on it, so the spacing is enforced
        against the previous call that actually went out — not against a nominal reservation that a
        short sleep (Windows timer granularity is ~15 ms) could undershoot. The sleep loops until the
        interval has truly elapsed by `time.monotonic`. Other hosts have their own Throttle and lock, so
        pacing one host never delays another."""
        t0 = _monotonic()
        with self._lock:
            if self._last_admitted is not None:
                target = self._last_admitted + self.min_interval_s
                while True:
                    now = _monotonic()
                    if now >= target:
                        break
                    _sleep(target - now)
            self._last_admitted = _monotonic()
            return max(0.0, self._last_admitted - t0)


_REGISTRY = {}
_REGISTRY_LOCK = threading.Lock()


def get_throttle(host, min_interval_s=None):
    """Process-global Throttle for `host`. Creates it on first sight (interval required then); a later
    call with an interval updates the shared object. Raises ValueError if the host is unknown and no
    interval was given — a throttle with an undeclared interval is a default in disguise."""
    with _REGISTRY_LOCK:
        t = _REGISTRY.get(host)
        if t is None:
            if min_interval_s is None:
                raise ValueError(f"get_throttle({host!r}): first registration needs min_interval_s")
            t = Throttle(host, min_interval_s)
            _REGISTRY[host] = t
        elif min_interval_s is not None and float(min_interval_s) != t.min_interval_s:
            t.set_min_interval(min_interval_s)
        return t


def parse_retry_after(value):
    """Seconds from a Retry-After header. Integer form only (RFC 7231 §7.1.3 also allows an HTTP-date;
    we do not parse dates — the caller falls back to DEFAULT_RETRY_WAIT_S, declared). Returns None when
    unusable. Clamped to [0, MAX_RETRY_AFTER_S]."""
    if value is None:
        return None
    try:
        secs = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if secs < 0:
        return None
    return min(secs, MAX_RETRY_AFTER_S)


def _header(err, name):
    hdrs = getattr(err, "headers", None)
    if hdrs is None:
        return None
    try:
        return hdrs.get(name)
    except Exception:
        return None


def retry_once_on_429(fn, stats=None):
    """Call fn(); on HTTP 429 wait (Retry-After or DEFAULT_RETRY_WAIT_S) and call fn() exactly once more.

    `stats` (optional dict) receives what happened, for the caller's ledger:
        retries_429      0 or 1
        retry_after_s    seconds waited before the retry (None when no retry)
        retry_after_src  'header' | 'default' | None
    A second 429 — or any non-429 error — propagates unchanged. ONE retry, never a loop (CLAUDE.md §6)."""
    if stats is not None:
        stats.update({"retries_429": 0, "retry_after_s": None, "retry_after_src": None})
    try:
        return fn()
    except urllib.error.HTTPError as e:
        if getattr(e, "code", None) != 429:
            raise
        secs = parse_retry_after(_header(e, "Retry-After"))
        src = "header"
        if secs is None:
            secs, src = DEFAULT_RETRY_WAIT_S, "default"
        if stats is not None:
            stats.update({"retries_429": 1, "retry_after_s": secs, "retry_after_src": src})
        if secs > 0:
            _sleep(secs)
        return fn()
