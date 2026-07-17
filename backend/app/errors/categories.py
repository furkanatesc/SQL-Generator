"""Hata kategorileri (Sprint 27.2).

Kategori, hatanın DOĞASIDIR ve koda ait SABİT bir özelliktir.
Hatanın nerede yakalandığı (stage) AYRI bir eksendir ve çalışma zamanı
verisidir — registry'ye girmez, hata dict'lerindeki "stage" alanında yaşar.

Bu ayrım v1'in asıl kusurunun düzeltmesidir: v1'de "semantic_validation" hem
bir stage hem bir error type'tı. Ayrıca aynı kod (ör. missing_column) hem
semantic validation'da hem execution'da doğabilir; doğası aynıdır, yakalandığı
yer farklıdır.
"""
from enum import StrEnum


class ErrorCategory(StrEnum):
    INPUT = "input"
    RETRIEVAL = "retrieval"
    GENERATION = "generation"
    VALIDATION = "validation"
    SECURITY = "security"
    EXECUTION = "execution"
    INTERNAL = "internal"
