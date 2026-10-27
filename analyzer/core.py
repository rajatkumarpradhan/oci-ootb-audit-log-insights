"""Insights from OCI Audit log events read from local files (offline, stdlib only).

OCI Audit records every API call in a tenancy as a JSON log event. When those
events are archived to Object Storage (see docs/setup.md) or downloaded by
hand, they arrive as JSON-lines files, optionally gzipped. This module parses
the documented event shape and summarizes who did what, from where, and what
was denied. It makes no API calls and never touches a live tenancy.
"""
from __future__ import annotations

import gzip
import json
import os
from collections import Counter
from datetime import datetime, timezone

WRITE_ACTIONS = {"POST", "PUT", "DELETE", "PATCH"}


class InputError(ValueError):
    pass


def parse_time(value):
    """OCI audit 'datetime' is ms-since-epoch; tolerate ISO strings too."""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _events_from_text(text, source, stats):
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            stats["bad_lines"] += 1
            continue
        items = obj if isinstance(obj, list) else [obj]
        for it in items:
            if isinstance(it, dict) and isinstance(it.get("data"), dict):
                yield it
            else:
                stats["skipped"] += 1


def iter_events(paths, stats=None):
    """Yield audit events from .jsonl/.json/.gz files or directories of them."""
    if stats is None:
        stats = Counter()
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += [os.path.join(p, f) for f in sorted(os.listdir(p))]
        else:
            files.append(p)
    if not files:
        raise InputError(f"no input files in: {', '.join(paths)}")
    found = False
    for f in files:
        if not os.path.isfile(f):
            stats["missing"] += 1
            continue
        found = True
        if f.endswith(".gz"):
            with gzip.open(f, "rt", encoding="utf-8", errors="replace") as fh:
                yield from _events_from_text(fh.read(), f, stats)
        else:
            with open(f, encoding="utf-8", errors="replace") as fh:
                yield from _events_from_text(fh.read(), f, stats)
    if not found:
        raise InputError(f"no readable files in: {', '.join(paths)}")


def summarize(events, top=5):
    """Build the insights report from an iterable of audit events."""
    principals, ips, names, statuses, per_day = Counter(), Counter(), Counter(), Counter(), Counter()
    denials, writes = [], 0
    first = last = None
    total = 0
    for ev in events:
        total += 1
        data = ev.get("data", {})
        ident = data.get("identity") or {}
        req = data.get("request") or {}
        resp = data.get("response") or {}
        ts = parse_time(ev.get("datetime"))
        if ts:
            first = ts if first is None or ts < first else first
            last = ts if last is None or ts > last else last
            per_day[ts.date().isoformat()] += 1
        principals[ident.get("principalName") or "<unknown>"] += 1
        ips[ident.get("ipAddress") or "<unknown>"] += 1
        names[data.get("eventName") or "<unknown>"] += 1
        status = str(resp.get("status") or "?")
        statuses[status] += 1
        if status.startswith("4"):
            denials.append({
                "time": ts.isoformat() if ts else "?",
                "principal": ident.get("principalName") or "<unknown>",
                "event": data.get("eventName") or "?",
                "status": status,
            })
        if str(req.get("action", "")).upper() in WRITE_ACTIONS:
            writes += 1
    return {
        "total_events": total,
        "first_event": first.isoformat() if first else None,
        "last_event": last.isoformat() if last else None,
        "top_principals": principals.most_common(top),
        "top_source_ips": ips.most_common(top),
        "top_operations": names.most_common(top),
        "response_statuses": dict(statuses.most_common()),
        "write_operations": writes,
        "denied_count": len(denials),
        "denials": denials[:top],
        "events_per_day": dict(sorted(per_day.items())),
    }


def _rows(title, pairs, fmt="    {:<40} {}"):
    lines = [f"  {title}"]
    if not pairs:
        lines.append("    (none)")
    for k, v in pairs:
        lines.append(fmt.format(k, v))
    return lines


def render(rep):
    """Human-readable report text."""
    out = ["OCI Audit log insights (offline analysis of archived events)",
           f"  events analyzed: {rep['total_events']}",
           f"  time range: {rep['first_event'] or '?'} .. {rep['last_event'] or '?'}",
           f"  write operations (POST/PUT/DELETE/PATCH): {rep['write_operations']}",
           f"  denied responses (4xx): {rep['denied_count']}"]
    out += _rows("top principals:", rep["top_principals"])
    out += _rows("top source IPs:", rep["top_source_ips"])
    out += _rows("top operations:", rep["top_operations"])
    out += _rows("response statuses:", list(rep["response_statuses"].items()))
    if rep["denials"]:
        out.append("  recent denials:")
        for d in rep["denials"]:
            out.append(f"    {d['time']} {d['principal']} {d['event']} -> {d['status']}")
    if rep["events_per_day"]:
        out.append("  events per day:")
        for day, n in rep["events_per_day"].items():
            out.append(f"    {day}  {'#' * min(n, 40)} {n}")
    return "\n".join(out)
