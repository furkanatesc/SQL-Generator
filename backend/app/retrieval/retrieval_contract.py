from dataclasses import dataclass
from typing import Literal, Tuple

RETRIEVAL_VERSION = "top_k_retrieval_v1"

RetrievalObjectType = Literal["table", "column", "relationship"]


@dataclass(frozen=True)
class RetrievalQuery:
    """
    DTO carrying the query text, semantic query vector, count k,
    allowed object types filter, and vector space metadata to validate
    against compared embedding records.
    """
    query_text: str
    query_vector: Tuple[float, ...]
    k: int
    provider_id: str
    model_id: str
    dimension: int
    allowed_object_types: Tuple[RetrievalObjectType, ...] = (
        "table",
        "column",
        "relationship",
    )


@dataclass(frozen=True)
class RetrievalCandidate:
    """
    DTO representing a single retrieved schema object candidate
    with rank, score, and original database schema summary metadata.
    Does not carry the query or candidate vector to minimize payload overhead.
    """
    id: str
    object_id: str
    object_type: RetrievalObjectType
    text: str
    score: float
    rank: int
    summary_version: str
    schema_hash: str
    provider_id: str
    model_id: str
    dimension: int


@dataclass(frozen=True)
class TopKRetrievalResult:
    """
    DTO grouping Top-K retrieval results including original request text,
    count parameters, returned candidate lists, and contract version.
    """
    query_text: str
    k_requested: int
    k_returned: int
    candidates: Tuple[RetrievalCandidate, ...]
    retrieval_version: str = RETRIEVAL_VERSION
