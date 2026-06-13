import math
from typing import Protocol, Sequence, List
from app.retrieval.embedding_cache import EmbeddingRecord
from app.retrieval.retrieval_contract import RetrievalQuery, RetrievalCandidate, TopKRetrievalResult
from app.retrieval.similarity import cosine_similarity
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError

class TopKRetriever(Protocol):
    """
    Protocol defining the contract for retriever backends.
    """
    def retrieve(
        self,
        query: RetrievalQuery,
        records: Sequence[EmbeddingRecord]
    ) -> TopKRetrievalResult:
        """
        Retrieves top-K candidates from a sequence of embedding records.
        """
        ...


class InMemoryTopKRetriever:
    """
    Deterministic in-memory implementation of the TopKRetriever protocol.
    Runs entirely offline with zero network dependency.
    """
    def retrieve(
        self,
        query: RetrievalQuery,
        records: Sequence[EmbeddingRecord]
    ) -> TopKRetrievalResult:
        # 1. Validation
        if query.k <= 0:
            raise EmbeddingNonRetryableError(f"k must be greater than zero, got k={query.k}")
            
        if not query.allowed_object_types:
            raise EmbeddingNonRetryableError("allowed_object_types cannot be empty.")
            
        # Zero-norm check on query vector
        query_norm = math.sqrt(sum(x * x for x in query.query_vector))
        if query_norm < 1e-9:
            raise EmbeddingNonRetryableError("Query vector cannot be a zero-norm vector.")

        # Duplicate checking and dimension check on records
        seen_ids = set()
        for rec in records:
            if rec.id in seen_ids:
                raise EmbeddingNonRetryableError(f"Duplicate candidate ID detected in records: {rec.id}")
            seen_ids.add(rec.id)
            
            if len(rec.vector) != rec.dimension:
                raise EmbeddingNonRetryableError(
                    f"Dimension mismatch in record {rec.id}: expected={rec.dimension}, actual={len(rec.vector)}"
                )
            
            if len(rec.vector) != len(query.query_vector):
                raise EmbeddingNonRetryableError(
                    f"Dimension mismatch between query and record {rec.id}: "
                    f"query_dimension={len(query.query_vector)}, record_dimension={len(rec.vector)}"
                )

        # 2. Filter records by allowed_object_types
        candidates = []
        for rec in records:
            if rec.id.startswith("table:"):
                obj_type = "table"
            elif rec.id.startswith("column:"):
                obj_type = "column"
            elif rec.id.startswith("relationship:"):
                obj_type = "relationship"
            else:
                raise EmbeddingNonRetryableError(f"Unknown object type prefix in record ID: {rec.id}")

            if obj_type not in query.allowed_object_types:
                continue

            # Compute similarity
            score = cosine_similarity(query.query_vector, rec.vector)
            
            # Map object_id by splitting at the first colon
            parts = rec.id.split(":", 1)
            if len(parts) < 2:
                raise EmbeddingNonRetryableError(f"Malformed record ID: {rec.id}")
            object_id = parts[1]

            candidates.append((score, rec, obj_type, object_id))

        # 3. Sort candidates deterministically: score descending, then record ID ascending
        candidates.sort(key=lambda item: item[1].id)
        candidates.sort(key=lambda item: item[0], reverse=True)

        # 4. Limit to K and construct RetrievalCandidates
        top_k = candidates[:query.k]
        ret_candidates = []
        for rank_idx, (score, rec, obj_type, object_id) in enumerate(top_k):
            ret_candidates.append(RetrievalCandidate(
                id=rec.id,
                object_id=object_id,
                object_type=obj_type,
                text=rec.text,
                score=score,
                rank=rank_idx + 1,
                summary_version=rec.summary_version,
                schema_hash=rec.schema_hash,
                provider_id=rec.provider_id,
                model_id=rec.model_id,
                dimension=rec.dimension
            ))

        return TopKRetrievalResult(
            query_text=query.query_text,
            k_requested=query.k,
            k_returned=len(ret_candidates),
            candidates=tuple(ret_candidates)
        )
