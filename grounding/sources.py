"""sources.py: one generator per source. Each yields rows {text, source, ref, ...payload}.

A source raises instead of yielding nothing: the refresh keeps the last build of a source that fails.
Swap the bodies for your own systems; the row shape is the only contract.
"""
import glob, json, os, re

from fieldkit import bridge

FIX = os.environ.get("GROUNDING_FIXTURES") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures")
TICKETS = ("mcp__helpdesk__search_tickets", {"query": "status:open"})   # a call only a connector session can make


class Pending(Exception):
    """The source is queued for a connector and has never been fulfilled."""


def docs():
    """Product docs: one row per sentence, so an answer cites a fact and not a page."""
    for p in sorted(glob.glob(os.path.join(FIX, "docs", "*.md"))):
        page, section = os.path.basename(p)[:-3], ""
        for line in open(p):
            line = line.strip()
            if line.startswith("#"):
                section = line.lstrip("# ")
                continue
            for s in re.split(r"(?<=[.!?])\s+", line):
                if len(s.split()) >= 5:
                    yield {"text": s, "source": "docs", "ref": f"docs/{page}", "section": section}


def field():
    """Field notes: what customers said, described by segment and vertical, never by name."""
    for c in json.load(open(os.path.join(FIX, "field", "calls.json"))):
        yield {"text": c["text"], "source": "field", "ref": c["id"], "segment": c["segment"], "vertical": c["vertical"]}


def tickets():
    """Support tickets through the bridge: queue the call, serve the last extract a session stored."""
    key, have = bridge.queue(*TICKETS)
    if not have:
        raise Pending(f"queued as {key}; fulfil it from a connector session, then re-run")
    for t in have["result"]["tickets"]:
        yield {"text": t["summary"], "source": "tickets", "ref": t["id"]}


ALL = {"docs": docs, "field": field, "tickets": tickets}
