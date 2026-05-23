from typing import Dict, Any, List, Set, Tuple
from app.schema_graph.backend import SchemaGraphBackend
from app.schema_graph.traversal_policy import TraversalPolicy
from app.schema_graph.token_budget import TokenBudgetEstimator
from app.schema_graph.hub_detector import HubDetector
from app.schema_candidates import CandidateAggregate

class GraphPruner:
    def __init__(
        self,
        graph_backend: SchemaGraphBackend,
        budget_estimator: TokenBudgetEstimator,
        hub_detector: HubDetector,
    ):
        self.graph_backend = graph_backend
        self.budget_estimator = budget_estimator
        self.hub_detector = hub_detector

    def _try_add_table(
        self,
        table: str,
        phase: str,
        schema: Dict[str, Any],
        selected_tables: Set[str],
        current_cost: int,
        policy: TraversalPolicy,
        trace: Dict[str, Any],
    ) -> Tuple[bool, int]:
        if table not in schema["tables"]:
            return False, current_cost

        if table in selected_tables:
            return False, current_cost

        if len(selected_tables) >= policy.max_tables:
            trace["skipped_max_tables"].append({
                "table": table,
                "phase": phase,
                "max_tables": policy.max_tables,
                "reason": "max_tables_reached",
            })
            return False, current_cost

        table_cost = self.budget_estimator.estimate_table_cost(
            table,
            schema["tables"][table],
        )

        if not self.budget_estimator.can_add(
            current_cost,
            table_cost,
            policy.token_budget,
        ):
            trace["skipped_budget"].append({
                "table": table,
                "phase": phase,
                "cost": table_cost,
                "current_cost": current_cost,
                "budget": policy.token_budget,
                "reason": "token_budget_exceeded",
            })
            return False, current_cost

        selected_tables.add(table)
        return True, current_cost + table_cost

    def select_subgraph(
        self,
        schema: Dict[str, Any],
        candidates: List[CandidateAggregate],
        policy: TraversalPolicy,
    ) -> Tuple[Set[str], Dict[str, Any]]:
        self.graph_backend.build_graph(schema)

        hub_reasons = self.hub_detector.detect_hub_reasons(schema)
        hub_tables = set(hub_reasons.keys())

        graph_trace = {
            "policy": policy.__dict__,
            "path_mode": policy.path_mode,
            "hub_tables": [
                {"table": table, "reasons": reasons}
                for table, reasons in hub_reasons.items()
            ],
            "seed_candidates": [],
            "seed_tables": [],
            "expanded_neighbors": [],
            "skipped_hubs": [],
            "skipped_budget": [],
            "skipped_max_tables": [],
            "path_repairs": [],
            "estimated_tokens": 0,
            "selected_tables": []
        }

        selected_tables: Set[str] = set()
        current_cost = 0

        # Seed candidates selection
        seeds = [
            candidate
            for candidate in candidates
            if candidate.score >= policy.min_candidate_score
        ]
        seeds.sort(key=lambda c: c.score, reverse=True)

        graph_trace["seed_candidates"] = [
            {"table": c.table, "score": c.score}
            for c in seeds
        ]

        # Adding seed tables
        for c in seeds:
            added, current_cost = self._try_add_table(
                table=c.table,
                phase="seed_selection",
                schema=schema,
                selected_tables=selected_tables,
                current_cost=current_cost,
                policy=policy,
                trace=graph_trace
            )
            if added:
                graph_trace["seed_tables"].append(c.table)

        # Bounded BFS expansion
        queue = [(c.table, 0) for c in seeds if c.table in selected_tables]

        while queue:
            current_table, depth = queue.pop(0)

            if depth >= policy.max_depth:
                continue

            neighbors = self.graph_backend.top_neighbors(
                current_table,
                limit=policy.max_neighbors_per_seed,
                min_weight=policy.min_edge_weight,
            )

            for neighbor in neighbors:
                if neighbor in selected_tables:
                    continue

                if policy.exclude_hubs and neighbor in hub_tables:
                    graph_trace["skipped_hubs"].append({
                        "table": neighbor,
                        "phase": "expansion",
                        "reason": "hub_expansion_blocked",
                    })
                    continue

                added, current_cost = self._try_add_table(
                    table=neighbor,
                    phase="expansion",
                    schema=schema,
                    selected_tables=selected_tables,
                    current_cost=current_cost,
                    policy=policy,
                    trace=graph_trace
                )

                if added:
                    graph_trace["expanded_neighbors"].append({
                        "from": current_table,
                        "to": neighbor,
                        "depth": depth + 1,
                    })
                    queue.append((neighbor, depth + 1))

        # Path repair
        selected_list = list(selected_tables)
        for i in range(len(selected_list)):
            for j in range(i + 1, len(selected_list)):
                source = selected_list[i]
                target = selected_list[j]

                path = self.graph_backend.shortest_path(
                    source,
                    target,
                    weight="cost",
                    mode=policy.path_mode,
                )

                if not path:
                    continue

                added_nodes = []
                skipped_nodes = []

                for node in path:
                    if node in selected_tables:
                        continue

                    if node in hub_tables:
                        if policy.allow_hubs_as_connectors:
                            pass
                        elif policy.exclude_hubs:
                            graph_trace["skipped_hubs"].append({
                                "table": node,
                                "phase": "path_repair",
                                "reason": "hub_connector_not_allowed",
                            })
                            skipped_nodes.append(node)
                            continue

                    added, current_cost = self._try_add_table(
                        table=node,
                        phase="path_repair",
                        schema=schema,
                        selected_tables=selected_tables,
                        current_cost=current_cost,
                        policy=policy,
                        trace=graph_trace
                    )

                    if added:
                        added_nodes.append(node)

                if added_nodes or skipped_nodes:
                    graph_trace["path_repairs"].append({
                        "source": source,
                        "target": target,
                        "path": path,
                        "added": added_nodes,
                        "skipped": skipped_nodes,
                        "mode": policy.path_mode,
                    })

        graph_trace["estimated_tokens"] = current_cost
        graph_trace["selected_tables"] = list(selected_tables)

        return selected_tables, graph_trace
