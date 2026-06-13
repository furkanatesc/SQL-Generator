from dataclasses import dataclass
from typing import Literal, Tuple

SQL_GENERATION_INPUT_VERSION = "sql_generation_input_v1"

TargetDialect = Literal[
    "sqlite",
    "postgresql",
    "oracle",
]


@dataclass(frozen=True)
class SQLGenerationInputConfig:
    target_dialect: TargetDialect
    max_prompt_chars: int = 30000
    require_sql_only_output: bool = True
    allow_dml: bool = False
    allow_ddl: bool = False


@dataclass(frozen=True)
class SQLGenerationConstraint:
    name: str
    value: str


@dataclass(frozen=True)
class SQLGenerationInputResult:
    raw_query: str
    normalized_query: str
    intent_type: str

    target_dialect: TargetDialect
    rendered_prompt: str
    prompt_sha256: str
    prompt_char_count: int

    constraints: Tuple[SQLGenerationConstraint, ...]
    source_section_types: Tuple[str, ...]
    source_item_ids: Tuple[str, ...]

    input_version: str = SQL_GENERATION_INPUT_VERSION
