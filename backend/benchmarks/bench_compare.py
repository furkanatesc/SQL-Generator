"""Sprint 28.0 — pure deterministic benchmark comparison (27.10 pattern).

Compares only the `deterministic` metric dicts (exact match, zero tolerance).
wall_ms is never read. No baseline -> bootstrap green.
"""


def _index(report: dict) -> dict:
    out = {}
    for mt in report["metrics"]:
        out[(mt["target"], mt["scale"])] = mt["deterministic"]
    return out


def compare_benchmark(current: dict, baseline) -> dict:
    if not baseline or not baseline.get("metrics"):
        return {"gate_passed": True, "bootstrap": True,
                "reason": "No baseline recorded yet (bootstrap)", "mismatches": []}

    cur = _index(current)
    base = _index(baseline)
    mismatches = []
    for key in sorted(set(cur) | set(base)):
        target, scale = key
        if key not in base:
            mismatches.append({"target": target, "scale": scale, "metric": "*",
                               "expected": "absent", "actual": "present"})
            continue
        if key not in cur:
            mismatches.append({"target": target, "scale": scale, "metric": "*",
                               "expected": "present", "actual": "absent"})
            continue
        cd, bd = cur[key], base[key]
        for name in sorted(set(cd) | set(bd)):
            if cd.get(name) != bd.get(name):
                mismatches.append({"target": target, "scale": scale, "metric": name,
                                   "expected": bd.get(name), "actual": cd.get(name)})

    return {"gate_passed": not mismatches, "bootstrap": False,
            "reason": "OK" if not mismatches else f"{len(mismatches)} deterministic metric mismatch(es)",
            "mismatches": mismatches}
