from dataclasses import dataclass
from typing import Literal, Tuple

RETRIEVAL_VERSION = "top_k_retrieval_v1"

RetrievalObjectType = Literal["table", "column", "relationship"]


@dataclass(frozen=True)
class RetrievalQuery:
    query_text: str
    query_vector: Tuple[float, ...]
    k: int
    allowed_object_types: Tuple[RetrievalObjectType, ...] = (
        "table",
        "column",
        "relationship",
    )


@dataclass(frozen=True)
class RetrievalCandidate:
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
    query_text: str
    k_requested: int
    k_returned: int
    candidates: Tuple[RetrievalCandidate, ...]
    retrieval_version: str = RETRIEVAL_VERSION
