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

from .filter import FILTER_MIN_BYTES, apply, heartbeat_line, ledger_line
from .rules import RULE_ORDER, STATELESS_RULES

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
    """Running totals — printed on exit, and emitted to the ledger as a heartbeat.

    `tool_results_seen` and `candidates` are the two fields that make this a health
    signal rather than a tally. They were already computed on every request and
    thrown away, and without them a filter that has quietly stopped doing anything
    is indistinguishable from a session with nothing to remove: see
    `filter.heartbeat_line` for the four failures that produce identical silence.

    `errors` is split because it was two different failures in one integer. An
    unreadable body says the wire format moved under the filter; a filter that
    raised says the filter has a bug. They call for different reactions and one
    counter could not ask for either.
    """

    requests: int = 0
    filtered: int = 0
    bytes_dropped: int = 0
    bytes_deferred: int = 0
    tool_results_seen: int = 0
    candidates: int = 0
    inflated: int = 0
    unreadable: int = 0
    filter_errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, *, filtered: bool = False, dropped: int = 0, deferred: int = 0,
               error: bool = False, unreadable: bool = False, results_seen: int = 0,
               candidates: int = 0, inflated: int = 0) -> int:
        """Count one request, and return the running request total.

        The total comes back so the caller can decide whether this request is the
        one that emits a heartbeat, without taking the lock a second time and
        without two threads reading a number between the increment and the check.
        """
        with self._lock:
            self.requests += 1
            self.filtered += int(filtered)
            self.bytes_dropped += dropped
            self.bytes_deferred += deferred
            self.tool_results_seen += results_seen
            self.candidates += candidates
            self.inflated += inflated
            self.unreadable += int(unreadable)
            self.filter_errors += int(error and not unreadable)
            return self.requests

    @property
    def errors(self) -> int:
        """Both failure kinds, for a caller that only wants to know if any."""
        return self.unreadable + self.filter_errors

    def counters(self) -> dict:
        """The heartbeat's payload. A snapshot under the lock, so a line never
        mixes a `requests` from one moment with a `filtered` from another."""
        with self._lock:
            return {
                "requests": self.requests,
                "filtered": self.filtered,
                "tool_results_seen": self.tool_results_seen,
                "candidates": self.candidates,
                "inflated": self.inflated,
                "bytes_dropped": self.bytes_dropped,
                "bytes_deferred": self.bytes_deferred,
                "unreadable": self.unreadable,
                "filter_errors": self.filter_errors,
            }

    def line(self) -> str:
        return (
            f"{self.requests} requests, {self.filtered} filtered, "
            f"{self.tool_results_seen:,} tool results seen, "
            f"{self.candidates:,} claimed, "
            f"{self.bytes_dropped:,} bytes dropped, "
            f"{self.bytes_deferred:,} deferred, "
            f"{self.inflated:,} refused by G4, "
            f"{self.unreadable} unreadable, {self.filter_errors} filter errors, "
            f"{self.errors} passthrough on error"
        )


# The kill switch. While this file exists the proxy keeps listening and keeps
# relaying, but stops rewriting anything — see `_filtering_disabled`.
DEFAULT_OFF_FILE = Path.home() / ".winnow" / "filter-off"


@dataclass
class Config:
    upstream: str = DEFAULT_UPSTREAM
    port: int = DEFAULT_PORT
    min_bytes: int = FILTER_MIN_BYTES
    keep_newest: int = 1
    ledger: Path | None = None
    verbose: bool = False
    off_file: Path | None = None
    # SPEC §8's rule selection, resolved once — `--tier`, `--rule`, `--no-rule`,
    # `rules.DISABLED_BY_DEFAULT` and `$WINNOW_RULES_OFF` — and held here for the
    # life of the process.
    #
    # Resolved at startup and never per request, and the distinction is the whole
    # of it. `rules.default_disabled` reads `os.environ` at call time, so a filter
    # that resolved per request would render the same conversation two ways the
    # moment somebody exported a variable in another shell: a prefix break arriving
    # from outside the process. A changed selection needs a restart, which is the
    # correct trade — the switch that works without one is `~/.winnow/filter-off`,
    # and it already exists.
    #
    # Why it has to exist at all: `docs/MILESTONE-2-VALIDATION.md` is written for
    # someone with no memory of this design, and its scorer prints
    # `export WINNOW_RULES_OFF=B2` as the remediation for a rule that fails its
    # precision bar. B2 is 96.07% of what this filter removes. Without this field
    # the pruner would stop firing that rule and the filter would go on firing it,
    # on a live request, with nothing anywhere saying so.
    rules: frozenset[str] = STATELESS_RULES
    # Write a heartbeat to the ledger every N requests; 0 turns it off. 200 is
    # about one line per twenty minutes of steady work on this install, against a
    # ledger already carrying 4.7 MB of removals — the cost is noise beside what
    # it makes visible. It needs a `--ledger`: there is nowhere else to put it,
    # and a periodic stderr line is the thing most likely to be lost in a terminal.
    heartbeat_every: int = 200


# Whether the last request saw the kill switch, so the transition is logged once
# rather than on every request.
_OFF_STATE = {"disabled": False}
_OFF_LOCK = threading.Lock()


def _filtering_disabled(config: Config) -> bool:
    """Is the kill switch on?

    Turning the *proxy* off is not the useful operation and cannot be done
    safely: `ANTHROPIC_BASE_URL` is fixed in the agent's environment when it is
    spawned, so a listener that goes away takes every request with it. What an
    operator actually needs is to stop the *rewriting* — and that is this. The
    socket stays open, requests keep flowing, and the bytes stop being touched.

    Checked per request, by design: a `touch` has to take effect on the next
    request rather than the next restart, or it is not a kill switch. One `stat`
    against an HTTPS round trip is not a cost worth optimising.
    """
    path = config.off_file
    if path is None:
        return False
    try:
        disabled = path.exists()
    except OSError:
        # An unreadable switch is not an off switch. Failing the other way would
        # let a permissions change silently disable the thing.
        return False
    with _OFF_LOCK:
        if disabled != _OFF_STATE["disabled"]:
            _OFF_STATE["disabled"] = disabled
            print(
                f"winnow: filtering {'DISABLED' if disabled else 're-enabled'} "
                f"by {path}; still relaying",
                file=sys.stderr,
            )
    return disabled


def _rewrite(raw: bytes, config: Config, stats: Stats) -> tuple[bytes, str | None]:
    """Apply the filter to one request body.

    Returns `(body, ledger line or None)`. Any failure returns the original
    bytes: SPEC §10's discipline is that this cannot be the thing that breaks a
    run, and a request it cannot parse is one it has no business editing.

    Every exit counts the request, including the ones where nothing was removed —
    that population is precisely what a health signal is about, and it is the one
    the ledger has never recorded.
    """
    try:
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise TypeError(f"request body is {type(body).__name__}, not an object")
    except (json.JSONDecodeError, TypeError, ValueError, UnicodeDecodeError) as exc:
        _count(config, stats, error=True, unreadable=True)
        print(f"winnow: forwarding unfiltered, unreadable body: {exc}", file=sys.stderr)
        return raw, None

    try:
        body, plan = apply(
            body,
            min_bytes=config.min_bytes,
            keep_newest=config.keep_newest,
            enabled=config.rules,
        )
    except Exception as exc:  # noqa: BLE001 — see the docstring: never break a run
        _count(config, stats, error=True)
        print(f"winnow: forwarding unfiltered, filter raised: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return raw, None

    seen = {
        "results_seen": plan.tool_results_seen,
        "candidates": len(plan.dropped) + len(plan.deferred),
        "inflated": plan.inflated,
    }
    if not plan.changed:
        _count(config, stats, **seen)
        return raw, None

    _count(config, stats, filtered=True, dropped=plan.bytes_dropped,
           deferred=plan.bytes_deferred, **seen)
    if config.verbose:
        print(f"winnow: dropped {len(plan.dropped)} results "
              f"({plan.bytes_dropped:,} bytes), deferred {len(plan.deferred)}",
              file=sys.stderr)
    return json.dumps(body).encode("utf-8"), ledger_line(plan)


def _count(config: Config, stats: Stats, **kw) -> None:
    """Record one request and, every `heartbeat_every` of them, write a heartbeat.

    Best effort in the strictest sense: `_append_ledger` catches its own errors
    and the request goes out either way. A counter must never be able to fail a
    request — §K6 — and this one is reached from every exit of `_rewrite`.
    """
    total = stats.record(**kw)
    every = config.heartbeat_every
    if every > 0 and config.ledger and total % every == 0:
        _append_ledger(config.ledger, heartbeat_line(stats.counters()), None)


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
        if _is_filtered(self.path) and raw and not _filtering_disabled(self.config):
            raw, ledger = _rewrite(raw, self.config, self.stats)
        elif raw:
            _count(self.config, self.stats)

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
        # A heartbeat answers no request, so it is not given one. Stamping
        # `request_id: null` on it would make it join to every session that
        # happens to have a record with no id.
        if "request_id" in record:
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
    # Which rules are on, said out loud. A component that fires a rule the
    # operator switched off elsewhere in the tool is SPEC §10's silent fallback
    # in its plainest form, and the operator who most needs to be told is the one
    # who exported `WINNOW_RULES_OFF` in another terminal an hour ago.
    on = ", ".join(rule for rule in RULE_ORDER if rule in config.rules) or "none"
    print(f"winnow: rules {on}", file=sys.stderr)
    if config.ledger and config.heartbeat_every > 0:
        print(f"winnow: heartbeat to the ledger every {config.heartbeat_every} "
              "requests, so a filter that has stopped filtering is visible "
              "without waiting for a bill", file=sys.stderr)
    if not config.rules:
        print("winnow: no rule is enabled, so nothing will be removed; the proxy "
              "is a plain relay", file=sys.stderr)
    if config.off_file:
        # Make the directory now, so the documented `touch` works. Without this
        # an operator reaching for the kill switch under load gets "No such file
        # or directory" from the one command they were told to run.
        try:
            config.off_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"winnow: cannot create {config.off_file.parent}: {exc}; "
                  "the kill switch needs that directory to exist", file=sys.stderr)
        print(f"winnow: stop filtering without a restart — touch {config.off_file}",
              file=sys.stderr)
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
        min_bytes=int(os.environ.get("WINNOW_FILTER_MIN_BYTES", str(FILTER_MIN_BYTES))),
        keep_newest=int(os.environ.get("WINNOW_FILTER_KEEP_NEWEST", "1")),
        verbose=os.environ.get("WINNOW_FILTER_VERBOSE") == "1",
        heartbeat_every=int(os.environ.get("WINNOW_FILTER_HEARTBEAT", "200")),
    )
    ledger = os.environ.get("WINNOW_FILTER_LEDGER")
    config.ledger = Path(ledger) if ledger else None
    off_file = os.environ.get("WINNOW_FILTER_OFF_FILE")
    config.off_file = Path(off_file) if off_file else DEFAULT_OFF_FILE
    for name, value in overrides.items():
        if value is not None:
            setattr(config, name, value)
    return config


def is_enabled() -> bool:
    """`WINNOW_FILTER=1` and nothing else. One toggle, as asked."""
    return os.environ.get("WINNOW_FILTER") == "1"
