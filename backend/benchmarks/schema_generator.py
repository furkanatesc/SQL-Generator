"""Sprint 28.0 — seeded synthetic large-schema generator (pure, deterministic).

Produces a legacy-dict schema (the same shape app.schema_manager emits) so the
benchmark can time from_legacy_schema (the validator target) and reuse the parsed
DatabaseSchema for the other three targets. All randomness via random.Random(seed).
"""
import random

# Stems chosen so get_singular(stem + "s") == stem (none end in 'e' or 's').
_BASE_STEMS = [
    "customer", "order", "product", "payment", "shipment",
    "region", "account", "ticket", "vendor", "contract",
    "project", "task", "asset", "item", "record",
    "category", "supplier", "worker", "location", "segment",
]


def _stem(i: int) -> str:
    base = _BASE_STEMS[i % len(_BASE_STEMS)]
    group = i // len(_BASE_STEMS)
    return base if group == 0 else f"{base}{group}"


def generate_schema(
    *,
    table_count: int,
    seed: int,
    fk_density: float = 0.6,
    hub_count: int = 3,
    dialect: str = "postgres",
) -> dict:
    rng = random.Random(seed)
    stems = [_stem(i) for i in range(table_count)]
    names = [s + "s" for s in stems]

    tables: dict = {}
    for i, name in enumerate(names):
        cols = [
            {"name": "id", "type": "integer", "primary_key": True},
            {"name": "name", "type": "text"},
            {"name": "status", "type": "text"},
            {"name": f"{stems[i]}_code", "type": "text"},
        ]
        fks: list = []
        if i >= hub_count:
            # (a) explicit FK to a random hub
            if rng.random() < fk_density:
                hub_idx = rng.randrange(hub_count)
                col_name = f"{stems[hub_idx]}_id"
                if all(c["name"] != col_name for c in cols):
                    cols.append({"name": col_name, "type": "integer"})
                    fks.append({
                        "column": col_name,
                        "referenced_table": names[hub_idx],
                        "referenced_column": "id",
                        "type": "explicit",
                    })
            # (b) implicit-only FK column to a random earlier non-hub table
            if i > hub_count and rng.random() < 0.5:
                parent_idx = rng.randrange(hub_count, i)
                col_name = f"{stems[parent_idx]}_id"
                if all(c["name"] != col_name for c in cols):
                    cols.append({"name": col_name, "type": "integer"})
        tables[name] = {"columns": cols, "foreign_keys": fks}

    return {"tables": tables}


_QUESTION_TEMPLATES = [
    "show all {a} with their {b}",
    "list {a} grouped by {b}",
    "count {a} for each {b}",
    "find {a} related to {b}",
]


def generate_join_path_pairs(table_names, *, seed, count=20):
    rng = random.Random(seed + 1)
    n = len(table_names)
    pairs = []
    while len(pairs) < count and n > 1:
        s = table_names[rng.randrange(n)]
        t = table_names[rng.randrange(n)]
        if s != t:
            pairs.append((s, t))
    return pairs


def generate_selection_questions(table_names, *, seed, count=20):
    rng = random.Random(seed + 2)
    n = len(table_names)
    questions = []
    for _ in range(count):
        a = table_names[rng.randrange(n)]
        b = table_names[rng.randrange(n)]
        tmpl = _QUESTION_TEMPLATES[rng.randrange(len(_QUESTION_TEMPLATES))]
        questions.append(tmpl.format(a=a, b=b))
    return questions
