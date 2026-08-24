"""A local pass-through proxy that applies the intake filter on the wire.

Claude Code reads `ANTHROPIC_BASE_URL`, so pointing it at this process is the
whole integration — no plugin, no hook, no edit to the transcript. The filter
has to run here rather than in a hook because the decision it makes is *where
the cache breakpoint goes*, and a hook has no access to the request body.

Standard library only. `psutil` is the package's one dependency and it exists
for a reason recorded in `pyproject.toml`; adding an HTTP client for this would
retire the "zero external dependencies" claim that `COZEMPIC.md` §4 checks.

**What it deliberately does not do.** It does not retry, buffer a response,
inspect a response body, or persist anything but its own ledger. A response is
streamed through byte-for-byte, so a streamed `message_delta` reaches Claude
Code at the same time it would have without this in the path. On any failure to
parse or rewrite a request, the original bytes are forwarded unchanged: a filter
that cannot decide must not be able to break a session.

**Credentials pass through untouched and are never logged.** The proxy copies
the client's own auth headers upstream and holds none of its own. That is worth
stating because it is the real cost of this design: an operator running it has
put a process of their own in front of their own credentials.
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .filter import apply, ledger_line

DEFAULT_UPSTREAM = "https://api.anthropic.com"
# Not 8787: UsageFoundry's Discord relay binds 127.0.0.1:8787 inside the same
# container this runs in (`scripts/discord-relay.mjs:87`), and the second of two
# processes to want a port does not get a degraded service, it gets nothing.
DEFAULT_PORT = 8789

# Hop-by-hop headers belong to one connection and must not be relayed. Content
# lengths are recomputed because the body changes; `accept-encoding` is dropped
# so the upstream never compresses a stream this has to forward verbatim.
_SKIP_REQUEST_HEADERS = frozenset({
    "host", "content-length", "connection", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade",
    "accept-encoding",
})
_SKIP_RESPONSE_HEADERS = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-length",
    "content-encoding",
})

# Only the endpoint that carries a conversation is rewritten. Everything else —
# token counting, models, files, batches — is a straight relay, because a filter
# that rewrote a `count_tokens` body would make the count disagree with the
# request it was counting.
_FILTERED_PATHS = frozenset({"/v1/messages"})


def _is_filtered(path: str) -> bool:
    """Exact match on the path, query string discarded.

    Not a prefix test: `/v1/messages/count_tokens` starts with `/v1/messages`,
    and filtering it would make the count disagree with the request it counts —
    the caller would size a body the real request never sends.
    """
    return path.split("?", 1)[0].rstrip("/") in _FILTERED_PATHS


@dataclass
class Stats:
    """Running totals, printed on exit and readable while it runs."""

    requests: int = 0
    filtered: int = 0
    bytes_dropped: int = 0
    bytes_deferred: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, *, filtered: bool = False, dropped: int = 0, deferred: int = 0,
               error: bool = False) -> None:
        with self._lock:
            self.requests += 1
            self.filtered += int(filtered)
            self.bytes_dropped += dropped
            self.bytes_deferred += deferred
            self.errors += int(error)

    def line(self) -> str:
        return (
            f"{self.requests} requests, {self.filtered} filtered, "
            f"{self.bytes_dropped:,} bytes dropped, "
            f"{self.bytes_deferred:,} deferred, {self.errors} passthrough on error"
        )


@dataclass
class Config:
    upstream: str = DEFAULT_UPSTREAM
    port: int = DEFAULT_PORT
    min_bytes: int = 2048
    keep_newest: int = 1
    ledger: Path | None = None
    verbose: bool = False


def _rewrite(raw: bytes, config: Config, stats: Stats) -> tuple[bytes, str | None]:
    """Apply the filter to one request body.

    Returns `(body, ledger line or None)`. Any failure returns the original
    bytes: SPEC §10's discipline is that this cannot be the thing that breaks a
    run, and a request it cannot parse is one it has no business editing.
    """
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise TypeError(f"request body is {type(body).__name__}, not an object")
    except (json.JSONDecodeError, TypeError, ValueError, UnicodeDecodeError) as exc:
        stats.record(error=True)
        print(f"winnow: forwarding unfiltered, unreadable body: {exc}", file=sys.stderr)
        return raw, None

    try:
        body, plan = apply(body, min_bytes=config.min_bytes, keep_newest=config.keep_newest)
    except Exception as exc:  # noqa: BLE001 — see the docstring: never break a run
        stats.record(error=True)
        print(f"winnow: forwarding unfiltered, filter raised: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return raw, None

    if not plan.changed:
        stats.record()
        return raw, None

    stats.record(filtered=True, dropped=plan.bytes_dropped, deferred=plan.bytes_deferred)
    if config.verbose:
        print(f"winnow: dropped {len(plan.dropped)} results "
              f"({plan.bytes_dropped:,} bytes), deferred {len(plan.deferred)}",
              file=sys.stderr)
    return json.dumps(body).encode("utf-8"), ledger_line(plan)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    config: Config
    stats: Stats

    def log_message(self, fmt: str, *args) -> None:
        """Silence the default access log: it would put request lines carrying
        session identifiers onto stderr on every call."""

    def _relay(self) -> None:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""

        ledger = None
        if _is_filtered(self.path) and raw:
            raw, ledger = _rewrite(raw, self.config, self.stats)
        elif raw:
            self.stats.record()

        split = urlsplit(self.config.upstream)
        cls = http.client.HTTPSConnection if split.scheme == "https" else http.client.HTTPConnection
        conn = cls(split.netloc, timeout=900)
        try:
            headers = {
                name: value
                for name, value in self.headers.items()
                if name.lower() not in _SKIP_REQUEST_HEADERS
            }
            headers["Host"] = split.netloc
            if raw:
                headers["Content-Length"] = str(len(raw))
            conn.request(self.command, self.path, body=raw or None, headers=headers)
            upstream = conn.getresponse()
            if ledger and self.config.ledger:
                _append_ledger(self.config.ledger, ledger, upstream.getheader("request-id"))

            self.send_response(upstream.status)
            for name, value in upstream.getheaders():
                if name.lower() not in _SKIP_RESPONSE_HEADERS:
                    self.send_header(name, value)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            # Chunked, unbuffered: a streamed response has to arrive as it is
            # produced or the first token waits for the last.
            while True:
                chunk = upstream.read(8192)
                if not chunk:
                    break
                self.wfile.write(b"%X\r\n%s\r\n" % (len(chunk), chunk))
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except OSError as exc:
            print(f"winnow: upstream failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            try:
                self.send_error(502, "upstream unreachable")
            except OSError:
                pass
        finally:
            conn.close()

    do_POST = _relay
    do_GET = _relay
    do_DELETE = _relay


_LEDGER_LOCK = threading.Lock()


def _append_ledger(path: Path, line: str, request_id: str | None) -> None:
    """Append one line, best effort. A ledger that cannot be written is worth a
    line on stderr and nothing more — it is a record of what happened, not a
    precondition for it."""
    try:
        record = json.loads(line)
        record["request_id"] = request_id
        with _LEDGER_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
    except (OSError, json.JSONDecodeError) as exc:
        print(f"winnow: ledger not written: {exc}", file=sys.stderr)


def serve(config: Config) -> int:
    """Run until interrupted. Prints the one line an operator needs to wire it in."""
    handler = type("_BoundHandler", (_Handler,), {"config": config, "stats": Stats()})
    server = ThreadingHTTPServer(("127.0.0.1", config.port), handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"winnow: intake filter on {base} → {config.upstream}", file=sys.stderr)
    print(f"winnow: keep_newest={config.keep_newest} min_bytes={config.min_bytes}"
          + (f" ledger={config.ledger}" if config.ledger else ""), file=sys.stderr)
    print(f"\n  export ANTHROPIC_BASE_URL={base}\n", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        print(f"winnow: {handler.stats.line()}", file=sys.stderr)
    return 0


def config_from_env(**overrides) -> Config:
    """Settings come from the environment so the toggle is one variable.

    `WINNOW_FILTER=1` is the switch an operator flips; everything else has a
    default that works.
    """
    config = Config(
        upstream=os.environ.get("WINNOW_FILTER_UPSTREAM", DEFAULT_UPSTREAM),
        port=int(os.environ.get("WINNOW_FILTER_PORT", str(DEFAULT_PORT))),
        min_bytes=int(os.environ.get("WINNOW_FILTER_MIN_BYTES", "2048")),
        keep_newest=int(os.environ.get("WINNOW_FILTER_KEEP_NEWEST", "1")),
        verbose=os.environ.get("WINNOW_FILTER_VERBOSE") == "1",
    )
    ledger = os.environ.get("WINNOW_FILTER_LEDGER")
    config.ledger = Path(ledger) if ledger else None
    for name, value in overrides.items():
        if value is not None:
            setattr(config, name, value)
    return config


def is_enabled() -> bool:
    """`WINNOW_FILTER=1` and nothing else. One toggle, as asked."""
    return os.environ.get("WINNOW_FILTER") == "1"
