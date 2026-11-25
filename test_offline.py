"""Offline checks against an in-memory stand-in for the cluster. Run: python3 test_offline.py"""
import json, os, re, shutil, tempfile

from fieldkit import bridge, preflight, qdrant as Q

from grounding import refresh, sources

STORE = {}
words = lambda s: set(re.findall(r"[a-z0-9]+", s.lower()))


def _fake_cluster():
    STORE.clear()
    Q.hybrid_collection = lambda *a, **k: True
    Q.hybrid_point = lambda pid, text, payload: {"id": pid, "payload": payload}
    Q.upsert = lambda name, pts, **k: STORE.update({p["id"]: p for p in pts})
    Q.delete = lambda name, ids, **k: [STORE.pop(i) for i in ids]
    Q.scroll = lambda name, flt=None, **k: [p for p in list(STORE.values())
                                            if not flt or p["payload"]["source"] == flt["must"][0]["match"]["value"]]
    Q.hybrid_query = lambda name, q, limit=5, **k: sorted(STORE.values(), key=lambda p: -len(words(q) & words(p["payload"]["text"])))[:limit]
    preflight.qdrant = lambda: (True, "fake")
    bridge.EXTRACTS = tempfile.mkdtemp(); bridge.PENDING = os.path.join(bridge.EXTRACTS, "pending.jsonl")


def test_golden_targets_are_in_the_fixtures():
    have = {r["text"] for name in ("docs", "field") for r in sources.ALL[name]()}
    missing = [t for g in json.load(open(os.path.join(sources.FIX, "golden.json"))) for t in g["target"] if t not in have]
    assert not missing, missing


def test_refresh_is_incremental_prunes_and_survives_a_bad_source():
    _fake_cluster()
    log = []
    assert refresh.main(log.append) == [] and any("tickets: PENDING" in l for l in log)       # queued, not failed
    n = len(STORE)
    assert any("ceiling 1.00" in l for l in log)

    bridge.store(*sources.TICKETS, json.load(open(os.path.join(sources.FIX, "tickets-response.json"))))
    log.clear(); refresh.main(log.append)
    assert len(STORE) == n + 3 and any("docs: 0 new, 0 removed" in l for l in log)            # embed once

    fix = sources.FIX
    try:
        sources.FIX = tempfile.mkdtemp(); shutil.copytree(fix, sources.FIX, dirs_exist_ok=True)
        os.remove(os.path.join(sources.FIX, "docs", "regions.md"))                            # a page is retired
        open(os.path.join(sources.FIX, "field", "calls.json"), "w").write("[]")               # a fetch breaks
        log.clear()
        assert refresh.main(log.append) == ["field", "recall gate"]
        assert any("docs: 0 new, 3 removed" in l for l in log)                                # retired facts leave the index
        assert sum(p["payload"]["source"] == "field" for p in STORE.values()) == 6            # the broken source kept its last build
        assert any("not in the index" in l for l in log)                                      # and the gate names what went missing
    finally:
        sources.FIX = fix


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
