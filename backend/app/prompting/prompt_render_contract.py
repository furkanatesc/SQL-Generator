from dataclasses import dataclass
from typing import Tuple

PROMPT_RENDER_VERSION = "prompt_render_v1"


@dataclass(frozen=True)
class RenderedPromptSection:
    """
    DTO representing the final rendered text of a prompt section along with trace metadata.
    """
    section_type: str
    title: str
    rendered_text: str
    source_item_ids: Tuple[str, ...]
    required: bool


@dataclass(frozen=True)
class RenderedPromptResult:
    """
    DTO wrapping the full compiled prompt string and individual rendered sections.
    """
    raw_query: str
    normalized_query: str
    intent_type: str

    rendered_prompt: str
    rendered_sections: Tuple[RenderedPromptSection, ...]

    prompt_render_version: str = PROMPT_RENDER_VERSION
