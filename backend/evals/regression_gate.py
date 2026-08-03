"""Sürüm başına doğruluk regresyon kapısı — SAF çekirdek (Sprint 27.10).

I/O yok. datetime.now() ASLA (timestamp dışarıdan verilir). Golden eval raporunu
onceki surumun baseline'iyla kiyaslar: common = baseline∩current kesisimi uzerinden
per-case (sifir-tolerans birincil) + aggregate (ikincil) regresyon. Drift bilgi
amaclidir, kapiyi patlatmaz.
"""
from typing import Any, Optional

DEFAULT_REGRESSION_POLICY = {"max_pass_rate_drop": 0.0}


def compare_regression(current_report: dict, baseline: Optional[dict],
                       *, policy: Optional[dict] = None) -> dict:
    """Guncel golden raporu ile (varsa) baseline'i kiyaslayip regresyon sonucu dondurur.

    - baseline None/bos -> bootstrap: gate_passed=True.
    - Per-case (birincil, sifir-tolerans): common'da baseline'da GECEN ve simdi
      DUSEN case varsa -> regresyon.
    - Aggregate (ikincil): common uzerinden pass_rate dususu policy toleransini
      asarsa -> regresyon (per-case zaten tetiklediyse per-case sebebi onceliklidir).
    - Drift (new_cases/removed_cases/newly_passing) bilgi amaclidir.
    """
    effective = dict(DEFAULT_REGRESSION_POLICY)
    if policy:
        effective.update(policy)
    tolerance = effective["max_pass_rate_drop"]

    results = current_report["results"]
    current_ids = {r["id"] for r in results}
    current_passing = {r["id"] for r in results if r["passed"]}

    if not baseline:
        return {
            "gate_passed": True,
            "bootstrap": True,
            "reason": "No baseline recorded yet (bootstrap)",
            "baseline_version": None,
            "newly_failing": [],
            "newly_passing": [],
            "new_cases": sorted(current_ids),
            "removed_cases": [],
            "aggregate": {"baseline_pass_rate_common": 0.0,
                          "current_pass_rate_common": 0.0,
                          "drop": 0.0, "tolerance": tolerance},
            "summary": {"current_total": current_report["total"],
                        "current_pass_rate": current_report["pass_rate"],
                        "common_count": 0, "baseline_total": 0},
        }

    baseline_ids = set(baseline["case_ids"])
    baseline_passing = set(baseline["passing_case_ids"])
    common = baseline_ids & current_ids

    newly_failing = sorted(c for c in common
                           if c in baseline_passing and c not in current_passing)
    newly_passing = sorted(c for c in common
                           if c not in baseline_passing and c in current_passing)
    new_cases = sorted(current_ids - baseline_ids)
    removed_cases = sorted(baseline_ids - current_ids)

    if common:
        n = len(common)
        b_pass = len(baseline_passing & common)
        c_pass = len(current_passing & common)
        baseline_pr_common = b_pass / n
        current_pr_common = c_pass / n
        drop = (b_pass - c_pass) / n   # tam sayidan; FP artigi yok
    else:
        baseline_pr_common = 0.0
        current_pr_common = 0.0
        drop = 0.0

    reason = None
    if newly_failing:
        reason = "Previously-passing cases now failing"
    elif drop > tolerance:
        reason = "Aggregate pass rate dropped beyond tolerance"

    return {
        "gate_passed": reason is None,
        "bootstrap": False,
        "reason": reason,
        "baseline_version": baseline["version"],
        "newly_failing": newly_failing,
        "newly_passing": newly_passing,
        "new_cases": new_cases,
        "removed_cases": removed_cases,
        "aggregate": {"baseline_pass_rate_common": baseline_pr_common,
                      "current_pass_rate_common": current_pr_common,
                      "drop": drop, "tolerance": tolerance},
        "summary": {"current_total": current_report["total"],
                    "current_pass_rate": current_report["pass_rate"],
                    "common_count": len(common),
                    "baseline_total": baseline["total"]},
    }
