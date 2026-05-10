from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langgraph.managed.is_last_step import RemainingSteps


def _merge_dicts(a: dict | None, b: dict | None) -> dict:
    return {**(a or {}), **(b or {})}


def _add_lists(a: list | None, b: list | None) -> list:
    return (a or []) + (b or [])


class Artefact(TypedDict):
    id: str
    name: str
    # file | image | plotly | table | html | text
    type: Literal["file", "image", "plotly", "table", "html", "text"]
    content: str   # base64 for binary; JSON string for plotly/table; raw for html/text
    mime_type: str


class ModelConfig(TypedDict):
    provider: Literal["openai", "anthropic", "oss"]
    model: str
    temperature: float


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    # Required by create_react_agent in LangGraph ≥1.0
    remaining_steps: RemainingSteps
    # virtual FS: relative path → base64-encoded bytes
    virtual_files: Annotated[dict[str, str], _merge_dicts]
    # artefacts accumulate across steps
    artefacts: Annotated[list[Artefact], _add_lists]
    model_config: ModelConfig
