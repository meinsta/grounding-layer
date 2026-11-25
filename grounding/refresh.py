"""refresh.py: the scheduled run. Preflight, sync every source, then the recall gate.

Each source syncs on its own: a failed source keeps its last build and never blocks the others.
The recall gate runs last and is loud, so content drift shows up here and not in a thinner answer.

    python3 -m grounding.refresh                 # needs QDRANT_URL, QDRANT_API_KEY
    0 7 * * 1  cd <checkout> && python3 -m grounding.refresh >> refresh.log 2>&1
"""
import datetime, json, os, sys

from fieldkit import preflight, qdrant as Q, recall

from . import sources

COLL = os.environ.get("GROUNDING_COLLECTION", "grounding")
FLOOR = float(os.environ.get("GROUNDING_RECALL_FLOOR", "0.8"))
K = 5


def sync(source, rows):
    """Make the index match the source: embed only new rows, remove rows the source no longer has."""
    rows = list(rows)                           # a source that raises must raise before the index is touched
    if not rows:
        raise ValueError("0 rows")              # an empty fetch is a broken fetch; never prune the index to nothing
    want = {Q.point_id(source, r["ref"], r["text"]): r for r in rows}
    flt = {"must": [{"key": "source", "match": {"value": source}}]}
    have = {p["id"] for p in Q.scroll(COLL, flt=flt, with_payload=False)}
    new = [Q.hybrid_point(i, r["text"], r) for i, r in want.items() if i not in have]
    stale = sorted(have - set(want))
    Q.upsert(COLL, new)
    Q.delete(COLL, stale)
    return f"{len(new)} new, {len(stale)} removed, {len(want)} current"


def recall_gate():
    gold = json.load(open(os.path.join(sources.FIX, "golden.json")))
    r = recall.reach(target=[t for g in gold for t in g["target"]], queries=[g["q"] for g in gold],
                     fetch=lambda q: [p["payload"]["text"] for p in Q.hybrid_query(COLL, q, limit=K)],
                     corpus=[p["payload"]["text"] for p in Q.scroll(COLL)])
    line = f"reach {r['reached']}/{r['target']} = {r['reach']:.2f}, ceiling {r['ceiling']:.2f}"
    if r["not_in_index"]:                       # a golden answer the index never held is an ingest bug at any score
        raise RuntimeError(f"{line}; not in the index: {r['not_in_index'][:3]}")
    if r["reach"] < FLOOR:
        raise RuntimeError(f"{line}; below the floor of {FLOOR}; missed: {r['missed'][:3]}")
    return line


def main(log=print):
    preflight.gate([("Qdrant", preflight.qdrant, True), ("Bridge", preflight.bridge, False)], log=log)
    Q.hybrid_collection(COLL, keyword_indexes=("source",))
    failed = []
    steps = [(name, lambda fn=fn, name=name: sync(name, fn())) for name, fn in sources.ALL.items()] + [("recall gate", recall_gate)]
    for name, fn in steps:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%FT%TZ")
        try:
            log(f"== {stamp} {name}: {fn()}")
        except sources.Pending as e:
            log(f"== {stamp} {name}: PENDING ({e})")
        except Exception as e:
            failed.append(name)
            log(f"== {stamp} {name}: FAILED, kept last build ({type(e).__name__}: {e})")
    return failed


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
