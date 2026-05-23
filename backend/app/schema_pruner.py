import os
import json
import re
import logging
import math
from typing import Dict, Any, List, Set, Tuple, Optional
from dataclasses import dataclass
from app.schema_manager import SchemaManager
from app.synonym_repository import SQLiteSynonymRepository, SynonymRule
from app.schema_lexicon import SchemaLexiconBuilder
from app.nlp.text_normalizer import TextNormalizer

logger = logging.getLogger("schema_pruner")

@dataclass
class Candidate:
    table: str
    score: float
    source: str
    reason: str
    trace_data: Dict[str, Any] = None

    def __hash__(self):
        return hash(self.table)
    
    def __eq__(self, other):
        if not isinstance(other, Candidate):
            return False
        return self.table == other.table

@dataclass
class TraversalPolicy:
    max_depth: int = 2
    max_neighbors_per_seed: int = 5
    min_edge_score: float = 0.50
    exclude_hubs: bool = True
    token_budget: int = 6000

class SchemaGraphBackend:
    def build_graph(self, schema: Dict[str, Any]):
        raise NotImplementedError

    def personalized_pagerank(self, seeds: Dict[str, float]) -> Dict[str, float]:
        raise NotImplementedError

    def shortest_path(self, source: str, target: str, weight: str = "cost") -> List[str]:
        raise NotImplementedError

    def top_neighbors(self, table: str, limit: int, min_weight: float) -> List[str]:
        raise NotImplementedError

class NetworkXGraphBackend(SchemaGraphBackend):
    def __init__(self):
        try:
            import networkx as nx
            self.nx = nx
        except ImportError:
            raise ImportError("NetworkX is required for NetworkXGraphBackend. Please install it using 'pip install networkx'")
        self.G = None

    def build_graph(self, schema: Dict[str, Any]):
        self.G = self.nx.DiGraph()
        
        tables = schema.get("tables", {})
        edges = schema.get("graph", {}).get("edges", [])
        
        degrees = {}
        for edge in edges:
            u, v = edge["source"], edge["target"]
            degrees[u] = degrees.get(u, 0) + 1
            degrees[v] = degrees.get(v, 0) + 1

        for table in tables.keys():
            self.G.add_node(table)
            
        for edge in edges:
            u = edge["source"]
            v = edge["target"]
            
            weight = 1.0
            
            # Hub penalty
            target_degree = degrees.get(v, 0)
            if target_degree > 0:
                degree_penalty = 1 / math.log(2 + target_degree)
                weight *= degree_penalty
                
            cost = -math.log(weight + 1e-9)
            if not self.G.has_edge(u, v):
                self.G.add_edge(u, v, weight=weight, cost=cost)

    def personalized_pagerank(self, seeds: Dict[str, float]) -> Dict[str, float]:
        if not self.G or not seeds:
            return {}
            
        total_score = sum(seeds.values())
        if total_score == 0:
            return {}
            
        personalization = {k: v / total_score for k, v in seeds.items()}
        
        for node in self.G.nodes():
            if node not in personalization:
                personalization[node] = 0.0
                
        try:
            return self.nx.pagerank(self.G, alpha=0.85, personalization=personalization, weight='weight')
        except Exception as e:
            logger.error(f"PPR calculation failed: {e}")
            return {}

    def shortest_path(self, source: str, target: str, weight: str = "cost") -> List[str]:
        if not self.G:
            return []
        try:
            undirected_G = self.G.to_undirected()
            return self.nx.shortest_path(undirected_G, source=source, target=target, weight=weight)
        except self.nx.NetworkXNoPath:
            return []
        except Exception as e:
            logger.error(f"Shortest path failed: {e}")
            return []

    def top_neighbors(self, table: str, limit: int, min_weight: float) -> List[str]:
        if not self.G or table not in self.G:
            return []
        
        neighbors = []
        for n in self.G.to_undirected().neighbors(table):
            edge_data = self.G.get_edge_data(table, n) or self.G.get_edge_data(n, table)
            if edge_data and edge_data.get("weight", 0) >= min_weight:
                neighbors.append((n, edge_data.get("weight", 0)))
                
        neighbors.sort(key=lambda x: x[1], reverse=True)
        return [n for n, w in neighbors[:limit]]


class SchemaPruner:
    def __init__(self, schema_manager: SchemaManager = None, synonym_repository = None, normalizer: TextNormalizer = None):
        self.schema_manager = schema_manager or SchemaManager()
        self.graph_backend = NetworkXGraphBackend()
        self.synonym_repository = synonym_repository or SQLiteSynonymRepository()
        self.normalizer = normalizer or TextNormalizer()
        self.lexicon_builder = SchemaLexiconBuilder(normalizer=self.normalizer)
        
        self.HUB_TABLES = {"KULLANICI", "HASTANE", "KURUM", "PERSONEL", "BIRIM", "LOG", "PARAMETRE", "TANIM", "YETKI"}
        
    def _get_tokens(self, text: str) -> Set[str]:
        return self.normalizer.tokenize(text)

    def _jaccard_similarity(self, set1: Set[str], set2: Set[str]) -> float:
        if not set1 or not set2:
            return 0.0
        intersection = set1.intersection(set2)
        union = set1.union(set2)
        return len(intersection) / len(union)

    def _estimate_table_token_cost(self, table_meta: Dict[str, Any]) -> int:
        cost = 8
        cost += len(table_meta.get("columns", [])) * 3
        cost += len(table_meta.get("foreign_keys", [])) * 4
        return cost

    def resolve_entities(self, aqr: Dict[str, Any], schema: Dict[str, Any]) -> List[Candidate]:
        candidates: Dict[str, Candidate] = {}
        all_tables = list(schema["tables"].keys())
        query_text = aqr.get("natural_query", "")
        
        # Build lexicon for current schema
        lexicon = self.lexicon_builder.build_lexicon(schema)
        
        def add_candidate(table: str, score: float, source: str, reason: str, trace_data: Dict[str, Any] = None):
            if table in self.HUB_TABLES:
                score -= 0.3
            
            if table in candidates:
                if score > candidates[table].score:
                    candidates[table] = Candidate(table, score, source, reason, trace_data)
            else:
                if score > 0.0:
                    candidates[table] = Candidate(table, score, source, reason, trace_data)

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
                        
                        # Store rejected hits somewhere? For now we just don't add them as candidates.
                        # Wait, the user said "accepted/rejected RAG hits trace’e yazılacak".
                        # We can store them in a list inside self.rag_traces.
                        if not hasattr(self, 'rag_traces'):
                            self.rag_traces = []
                        self.rag_traces.append(trace_data)
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
        return valid_candidates

    def prune_schema(self, aqr: Dict[str, Any], force_refresh: bool = False, policy: TraversalPolicy = None) -> Dict[str, Any]:
        if policy is None:
            policy = TraversalPolicy()
            
        schema = self.schema_manager.load_schema(force_refresh=force_refresh)
        
        candidates = self.resolve_entities(aqr, schema)
        
        if not candidates:
            return {
                "pruned": False,
                "error": "Bu soru için ilgili tabloyu güvenle belirleyemedim. Lütfen sorgunuzu detaylandırın.",
                "original_table_count": len(schema["tables"]),
                "pruned_table_count": 0,
                "tables": {},
                "graph": {"nodes": [], "edges": []}
            }
            
        self.graph_backend.build_graph(schema)
        
        selected_tables = set()
        current_cost = 0
        
        # 1. Deterministic Bounded Traversal
        # Start with candidates that meet the minimum edge score (or high confidence)
        seeds = [c for c in candidates if c.score >= policy.min_edge_score]
        seeds.sort(key=lambda x: x.score, reverse=True)
        
        for c in seeds:
            tbl = c.table
            if tbl in schema["tables"] and tbl not in selected_tables:
                cost = self._estimate_table_token_cost(schema["tables"][tbl])
                if current_cost + cost <= policy.token_budget:
                    selected_tables.add(tbl)
                    current_cost += cost

        # 2. Bounded BFS Expansion
        queue = [(c.table, 0) for c in seeds if c.table in selected_tables] # (table, depth)
        
        while queue:
            current_table, depth = queue.pop(0)
            
            if depth >= policy.max_depth:
                continue
                
            neighbors = self.graph_backend.top_neighbors(
                current_table, 
                limit=policy.max_neighbors_per_seed, 
                min_weight=0.1 # graph weights are often penalized, so we use a low threshold for connectivity
            )
            
            for nbr in neighbors:
                if nbr in selected_tables:
                    continue
                    
                if policy.exclude_hubs and nbr in self.HUB_TABLES:
                    continue
                    
                if nbr in schema["tables"]:
                    cost = self._estimate_table_token_cost(schema["tables"][nbr])
                    if current_cost + cost <= policy.token_budget:
                        selected_tables.add(nbr)
                        current_cost += cost
                        queue.append((nbr, depth + 1))
                        
        # 3. Ensure shortest paths between disconnected selected tables
        selected_list = list(selected_tables)
        for i in range(len(selected_list)):
            for j in range(i+1, len(selected_list)):
                src, tgt = selected_list[i], selected_list[j]
                path = self.graph_backend.shortest_path(src, tgt)
                if path:
                    for p_node in path:
                        if p_node not in selected_tables:
                            if policy.exclude_hubs and p_node in self.HUB_TABLES:
                                continue # Don't connect through hubs if excluded
                            cost = self._estimate_table_token_cost(schema["tables"][p_node])
                            if current_cost + cost <= policy.token_budget:
                                selected_tables.add(p_node)
                                current_cost += cost
        
        pruned_schema = {
            "pruned": True,
            "original_table_count": len(schema["tables"]),
            "pruned_table_count": len(selected_tables),
            "estimated_tokens": current_cost,
            "debug_trace": {
                "rag_matches": getattr(self, 'rag_traces', []),
                "seed_candidates": [{"table": c.table, "score": c.score, "reason": c.reason, "trace_data": c.trace_data} for c in candidates],
                "selected_tables": list(selected_tables)
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
