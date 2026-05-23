import logging
from typing import Dict, Any, List, Set, Tuple
from dataclasses import dataclass, field
from app.schema_manager import SchemaManager
from app.synonym_repository import HybridSynonymRepository
from app.schema_lexicon import SchemaLexiconBuilder
from app.nlp.text_normalizer import TextNormalizer

logger = logging.getLogger("schema_pruner")

from app.schema_candidates import CandidateSignal, CandidateAggregate

from app.schema_graph import NetworkXGraphBackend, TraversalPolicy, TokenBudgetEstimator, HubDetector, GraphPruner


class SchemaPruner:
    def __init__(self, schema_manager: SchemaManager = None, synonym_repository = None, normalizer: TextNormalizer = None, graph_pruner = None):
        self.schema_manager = schema_manager or SchemaManager()
        self.normalizer = normalizer or TextNormalizer()
        self.synonym_repository = synonym_repository or HybridSynonymRepository(normalizer=self.normalizer)
        self.lexicon_builder = SchemaLexiconBuilder(normalizer=self.normalizer)
        
        self.graph_backend = NetworkXGraphBackend()
        self.budget_estimator = TokenBudgetEstimator()
        self.hub_detector = HubDetector(normalizer=self.normalizer)
        
        self.graph_pruner = graph_pruner or GraphPruner(
            graph_backend=self.graph_backend,
            budget_estimator=self.budget_estimator,
            hub_detector=self.hub_detector,
        )
        
    def _get_tokens(self, text: str) -> Set[str]:
        return self.normalizer.tokenize(text)

    def _jaccard_similarity(self, set1: Set[str], set2: Set[str]) -> float:
        if not set1 or not set2:
            return 0.0
        intersection = set1.intersection(set2)
        union = set1.union(set2)
        return len(intersection) / len(union)



    def resolve_entities(self, aqr: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[List[CandidateAggregate], Dict[str, Any]]:
        candidates: Dict[str, CandidateAggregate] = {}
        all_tables = list(schema["tables"].keys())
        query_text = aqr.get("natural_query", "")
        rag_traces = []
        
        # Build lexicon for current schema
        lexicon = self.lexicon_builder.build_lexicon(schema)
        
        hub_tables = self.hub_detector.detect_hubs(schema)
        
        def add_candidate(table: str, score: float, source: str, reason: str, trace_data: Dict[str, Any] = None):
            if table in hub_tables:
                # Apply hub penalty immediately to the signal score, or should it be on final score?
                # The user's prompt suggested subtracting 0.3 from candidate.score. Let's do it on the signal.
                score = max(score - 0.3, 0.0)
            
            if score <= 0.0:
                return
                
            if table not in candidates:
                candidates[table] = CandidateAggregate(table=table)
                
            candidates[table].add_signal(CandidateSignal(
                source=source,
                score=score,
                reason=reason,
                trace_data=trace_data
            ))

        # 0. Layer: RAG Embedding Retrieval
        if query_text:
            try:
                from app.rag_manager import RAGManager
                rag_manager = RAGManager()
                relevant_tables = rag_manager.search_ddl(query_text, limit=10)
                
                for idx, hit in enumerate(relevant_tables):
                    payload = hit.get("payload", {})
                    raw_score = hit.get("score")
                    
                    if raw_score is None:
                        continue
                        
                    table_name = payload.get("table_name")
                    if table_name:
                        # Qdrant with Cosine distance returns similarity (-1 to 1) where higher is better
                        normalized_score = raw_score
                        accepted = normalized_score >= 0.72
                        
                        trace_data = {
                            "table": table_name,
                            "raw_score": raw_score,
                            "normalized_score": normalized_score,
                            "score_mode": "similarity_higher_is_better",
                            "accepted": accepted
                        }
                        
                        if accepted:
                            add_candidate(table_name, normalized_score, "rag", f"Semantic match, score: {normalized_score:.3f}", trace_data)
                        
                        rag_traces.append(trace_data)
            except Exception as e:
                logger.error(f"[SchemaPruner] RAG retrieval failed: {e}")

        # 1. Layer: AQR "entities" Lexical Match
        for req_entity in aqr.get("entities", []):
            req_entity_clean = req_entity.strip().lower()
            req_tokens = self._get_tokens(req_entity_clean)
            
            expanded_tokens = set()
            for t in req_tokens:
                rules = self.synonym_repository.lookup(t)
                ignore = False
                for rule in rules:
                    if rule.target_type == 'ignore':
                        ignore = True
                        break
                    elif rule.target_type in ['concept', 'table']:
                        expanded_tokens.add(self.normalizer.normalize(rule.target_name))
                
                if not ignore:
                    expanded_tokens.add(t)
                    
                # Auto Schema Lexicon lookup
                if t in lexicon and not ignore:
                    if lexicon[t].get("can_seed", True):
                        for tbl in lexicon[t]["tables"]:
                            add_candidate(tbl, 0.8, "schema_lexicon", f"Auto lexicon match for '{t}'")
            
            for table in all_tables:
                table_lower = table.lower()
                table_tokens = self._get_tokens(table)
                
                if req_entity_clean == table_lower:
                    add_candidate(table, 1.0, "exact_table_match", f"Matched entity {req_entity_clean}")
                elif expanded_tokens.intersection(table_tokens):
                    jaccard = self._jaccard_similarity(expanded_tokens, table_tokens)
                    # Use original tokens for subset
                    if req_tokens and req_tokens.issubset(table_tokens):
                        add_candidate(table, 0.85, "subset_table_match", f"Tokens subset of {table}")
                    elif jaccard > 0.3:
                        add_candidate(table, 0.6 + jaccard*0.3, "synonym_table_match", f"Jaccard {jaccard:.2f}")

        # 2. Layer: Column and filter matches
        fields_to_check = []
        for f in aqr.get("fields", []) + aqr.get("sorts", []):
            if isinstance(f, dict) and "field" in f:
                fields_to_check.append(str(f["field"]).strip().lower())
            else:
                fields_to_check.append(str(f).strip().lower())
                
        for f in aqr.get("filters", []) + aqr.get("aggregations", []):
            if isinstance(f, dict):
                if "field" in f:
                    fields_to_check.append(str(f["field"]).strip().lower())
            else:
                fields_to_check.append(str(f).strip().lower())

        for field in fields_to_check:
            if "." in field:
                tbl_part = field.split(".")[0]
                for table in all_tables:
                    if tbl_part == table.lower():
                        add_candidate(table, 0.9, "exact_table_qualifier", f"Table qualifier {tbl_part}")
            else:
                for table, table_meta in schema["tables"].items():
                    for col in table_meta["columns"]:
                        if field == col["name"].lower():
                            add_candidate(table, 0.7, "exact_column_match", f"Matched column {field}")

        # 3. Layer: Value/Keyword matches
        rules_text = " ".join(aqr.get("business_rules", []))
        combined_text = f"{query_text} {rules_text}"
        tokens = self._get_tokens(combined_text)
        
        for token in tokens:
            rules = self.synonym_repository.lookup(token)
            search_tokens = {token}
            ignore = False
            for rule in rules:
                if rule.target_type == 'ignore':
                    ignore = True
                    break
                elif rule.target_type in ['concept', 'table']:
                    search_tokens.add(rule.target_name.lower())
                    
            if ignore:
                continue
                    
            for table in all_tables:
                table_tokens = self._get_tokens(table)
                if search_tokens.intersection(table_tokens):
                    add_candidate(table, 0.5, "keyword_table_match", f"Matched token {token}")
                
            for table, table_meta in schema["tables"].items():
                for col in table_meta["columns"]:
                    if search_tokens.intersection({col["name"].lower()}):
                        add_candidate(table, 0.4, "keyword_column_match", f"Matched column {token}")
                        
        valid_candidates = [c for c in candidates.values() if c.score >= 0.45]
        return valid_candidates, {"rag_matches": rag_traces}

    def prune_schema(self, aqr: Dict[str, Any], force_refresh: bool = False, policy: TraversalPolicy = None) -> Dict[str, Any]:
        if policy is None:
            policy = TraversalPolicy()
            
        schema = self.schema_manager.load_schema(force_refresh=force_refresh)
        
        candidates, resolve_trace = self.resolve_entities(aqr, schema)
        
        if not candidates:
            return {
                "pruned": False,
                "error": "Bu soru için ilgili tabloyu güvenle belirleyemedim. Lütfen sorgunuzu detaylandırın.",
                "original_table_count": len(schema["tables"]),
                "pruned_table_count": 0,
                "tables": {},
                "graph": {"nodes": [], "edges": []}
            }
            
        selected_tables, graph_trace = self.graph_pruner.select_subgraph(
            schema=schema,
            candidates=candidates,
            policy=policy,
        )
        
        return self._build_pruned_schema(
            schema=schema,
            selected_tables=selected_tables,
            graph_trace=graph_trace,
            resolve_trace=resolve_trace,
            candidates=candidates,
        )

    def _build_pruned_schema(
        self,
        schema: Dict[str, Any],
        selected_tables: Set[str],
        graph_trace: Dict[str, Any],
        resolve_trace: Dict[str, Any],
        candidates: List[CandidateAggregate]
    ) -> Dict[str, Any]:
        pruned_schema = {
            "pruned": True,
            "original_table_count": len(schema["tables"]),
            "pruned_table_count": len(selected_tables),
            "estimated_tokens": graph_trace.get("estimated_tokens", 0),
            "debug_trace": {
                "rag_matches": resolve_trace.get("rag_matches", []),
                "candidate_signals": [c.to_dict() for c in candidates],
                "selected_tables": list(selected_tables),
                "graph_trace": graph_trace
            },
            "tables": {},
            "graph": {
                "nodes": list(selected_tables),
                "edges": []
            }
        }
        
        for table in selected_tables:
            if table in schema["tables"]:
                original_table = schema["tables"][table]
                pruned_schema["tables"][table] = {
                    "columns": original_table["columns"],
                    "foreign_keys": []
                }
                
                for fk in original_table.get("foreign_keys", []):
                    ref_tbl = fk["referenced_table"]
                    if ref_tbl in selected_tables:
                        pruned_schema["tables"][table]["foreign_keys"].append(fk)
                        
        for edge in schema.get("graph", {}).get("edges", []):
            if edge["source"] in selected_tables and edge["target"] in selected_tables:
                pruned_schema["graph"]["edges"].append(edge)
                
        return pruned_schema
