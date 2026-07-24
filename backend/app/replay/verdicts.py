"""Replay verdict taksonomisi (Sprint 27.4).

Yaprak katman: stdlib disina import YOKTUR. Bu eksen 27.2'nin hata
taksonomisinden farklidir — burada soru "kod/sema degisince gecmis bir kosu
nasil degisti?"dir, "ne hata verdi?" degil.
"""
from enum import StrEnum

REPLAY_CONTRACT_VERSION = "query_replay_v1"


class ReplayVerdict(StrEnum):
    """Tek bir replay kosusunun sonucu.

    Birden fazla boyut ayni anda degisebilir; verdict EN CIDDI olani adlandirir,
    delta record'lari hepsini tasir (sessiz dusurme yok). Oncelik sirasi
    compare.py'de tanimlidir.
    """

    INPUT_UNAVAILABLE = "input_unavailable"
    BASELINE_UNAVAILABLE = "baseline_unavailable"
    REPLAY_FAILED = "replay_failed"
    SECURITY_REGRESSION = "security_regression"
    VALIDATION_REGRESSION = "validation_regression"
    RETRIEVAL_DRIFT = "retrieval_drift"
    VALIDATION_RECOVERY = "validation_recovery"
    SECURITY_RECOVERY = "security_recovery"
    IDENTICAL = "identical"
