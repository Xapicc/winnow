#!/usr/bin/env python3
"""Disposable. Answers the live-mode questions by observation rather than reasoning:
does a partially-written line ever appear at the end of a growing transcript, and how
long after a record's own timestamp does it become readable?

Polls every file in a directory tree at a very short interval, and for each poll records
  * total size
  * whether the final byte is a newline (i.e. a torn line is visible)
  * the length and a hash of any trailing fragment
When a complete new line appears, it prints the wall-clock delay between the timestamp
inside the record and the moment the reader could first see it.

usage: watch_partial.py <dir-or-file> <seconds> [interval_ms]
"""
import json, os, sys, time, glob

target = sys.argv[1]
duration = float(sys.argv[2])
interval = float(sys.argv[3]) / 1000 if len(sys.argv) > 3 else 0.002


def files():
    if os.path.isfile(target):
        return [target]
    return sorted(glob.glob(os.path.join(target, "**", "*.jsonl"), recursive=True))


state = {}          # path -> (size, consumed_offset)
torn_events = 0
torn_max = 0
torn_samples = []
lags = []
polls = 0
start = time.time()
deadline = start + duration

while time.time() < deadline:
    polls += 1
    for p in files():
        try:
            size = os.path.getsize(p)
        except OSError:
            continue
        prev_size, off = state.get(p, (None, size))
        if prev_size is None:
            state[p] = (size, size)      # start from the end: only watch new writes
            continue
        if size == prev_size:
            continue
        now = time.time()
        try:
            with open(p, "rb") as fh:
                fh.seek(off)
                chunk = fh.read()
        except OSError:
            continue
        if not chunk:
            state[p] = (size, off)
            continue
        tail_is_partial = not chunk.endswith(b"\n")
        if tail_is_partial:
            frag = chunk.rsplit(b"\n", 1)[-1]
            torn_events += 1
            torn_max = max(torn_max, len(frag))
            if len(torn_samples) < 5:
                torn_samples.append((os.path.basename(p), len(frag), frag[:60]))
            # do not advance past the fragment
            complete = chunk[: len(chunk) - len(frag)]
        else:
            complete = chunk
        for line in complete.split(b"\n"):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            ts = r.get("timestamp")
            if not ts:
                continue
            try:
                epoch = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")) \
                    - time.timezone + float("0." + (ts[20:23] or "0"))
            except Exception:
                continue
            lags.append((now - epoch, r.get("type"), os.path.basename(p)))
        state[p] = (size, off + len(complete))
    time.sleep(interval)

print(f"polls={polls} over {duration}s (interval {interval*1000:.1f}ms) "
      f"files={len(state)}")
print(f"torn-tail observations: {torn_events}  max fragment {torn_max} bytes")
for s in torn_samples:
    print("   ", s[0], s[1], "bytes:", s[2])
if lags:
    v = sorted(x[0] for x in lags)
    n = len(v)
    print(f"new records seen: {n}")
    print(f"  visibility lag vs record timestamp: min={v[0]*1000:.0f}ms "
          f"median={v[n//2]*1000:.0f}ms p90={v[9*n//10]*1000:.0f}ms max={v[-1]*1000:.0f}ms")
    kinds = {}
    for lag, t, _ in lags:
        kinds.setdefault(t, []).append(lag)
    for t, xs in sorted(kinds.items()):
        xs.sort()
        print(f"  {t:14} n={len(xs):4} median={xs[len(xs)//2]*1000:.0f}ms")
else:
    print("no new records observed")
