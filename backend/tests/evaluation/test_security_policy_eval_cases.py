from app.evaluation.security_policy_eval import run_security_eval, EvalAdjudicationStatus
from app.evaluation.security_policy_eval_cases import SECURITY_EVAL_CASES
from app.evaluation.security_policy_eval_projectors import (
    PROJECTOR_REGISTRY, CONTRACT_PERMISSION, CONTRACT_TENANT, CONTRACT_READ_ONLY,
    CONTRACT_RISK, CONTRACT_SENSITIVE, CONTRACT_PII_PHI, CONTRACT_AUDIT,
    CONTRACT_APPROVAL, CONTRACT_INJECTION, CONTRACT_RESULT_SET, CONTRACT_CREDENTIAL,
)

ALL_CONTRACTS = {
    CONTRACT_PERMISSION, CONTRACT_TENANT, CONTRACT_READ_ONLY, CONTRACT_RISK,
    CONTRACT_SENSITIVE, CONTRACT_PII_PHI, CONTRACT_AUDIT, CONTRACT_APPROVAL,
    CONTRACT_INJECTION, CONTRACT_RESULT_SET, CONTRACT_CREDENTIAL,
}


def test_every_contract_has_a_case():
    assert {c.contract_id for c in SECURITY_EVAL_CASES} == ALL_CONTRACTS


def test_case_ids_are_unique():
    ids = [c.case_id for c in SECURITY_EVAL_CASES]
    assert len(ids) == len(set(ids))


def test_shipped_suite_all_pass():
    run = run_security_eval(SECURITY_EVAL_CASES, PROJECTOR_REGISTRY)
    failures = [(r.case_id, r.mismatch_detail) for r in run.case_results if not r.passed]
    assert failures == [], failures
    assert run.failed == 0


def test_all_cases_approved():
    assert all(c.adjudication_status == EvalAdjudicationStatus.APPROVED
               for c in SECURITY_EVAL_CASES)
