"""Cliente de Claude acotado a lo que usa la app (respuestas con citas y tool use).

Expone eventos propios (``TextDelta``, ``Citation``, ``Done``) para que los servicios no dependan
de la forma de los eventos del SDK, y para poder reemplazarlo por ``FakeLlm`` en los tests.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic
from anthropic.types import CitationsSearchResultLocation


class LlmUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Citation:
    search_result_index: int
    start_block_index: int
    end_block_index: int
    cited_text: str


@dataclass(frozen=True)
class BlockEnd:
    """Fin de un bloque de texto: las citas recibidas se refieren al texto de ese bloque."""


@dataclass(frozen=True)
class Usage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    latency_ms: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class Done:
    usage: Usage
    stop_reason: str | None = None


@dataclass(frozen=True)
class ToolStart:
    name: str


@dataclass(frozen=True)
class TurnEnd:
    """Fin de un turno del agente: contenido completo (formato API) para el historial."""

    content: list[dict[str, Any]]
    stop_reason: str | None
    usage: Usage

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]


LlmEvent = TextDelta | Citation | BlockEnd | Done
TurnEvent = TextDelta | Citation | BlockEnd | ToolStart | TurnEnd


@dataclass
class ToolTurn:
    """Una respuesta del modelo en el bucle del agente."""

    content: list[dict[str, Any]]
    stop_reason: str | None
    usage: Usage
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class Llm(Protocol):
    def stream(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 2000,
    ) -> Iterator[LlmEvent]: ...

    def tool_turn(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4000,
    ) -> ToolTurn: ...

    def stream_turn(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4000,
    ) -> Iterator[TurnEvent]: ...


def _usage(model: str, usage: Any, started: float) -> Usage:
    return Usage(
        model=model,
        input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        latency_ms=int((time.perf_counter() - started) * 1000),
    )


class ClaudeLlm:
    def __init__(self, *, api_key: str | None, timeout: float) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)

    def stream(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        max_tokens: int = 2000,
    ) -> Iterator[LlmEvent]:
        started = time.perf_counter()
        try:
            with self._client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=messages,  # type: ignore[arg-type]
                output_config={"effort": "low"},
            ) as stream:
                for event in stream:
                    if event.type == "content_block_stop":
                        yield BlockEnd()
                        continue
                    if event.type != "content_block_delta":
                        continue
                    if event.delta.type == "text_delta":
                        yield TextDelta(event.delta.text)
                    elif event.delta.type == "citations_delta":
                        c = event.delta.citation
                        if isinstance(c, CitationsSearchResultLocation):
                            yield Citation(
                                search_result_index=c.search_result_index,
                                start_block_index=c.start_block_index,
                                end_block_index=c.end_block_index,
                                cited_text=c.cited_text,
                            )
                final = stream.get_final_message()
        except anthropic.APIError as exc:
            raise LlmUnavailableError(str(exc)) from exc
        yield Done(_usage(model, final.usage, started), final.stop_reason)

    def stream_turn(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4000,
    ) -> Iterator[TurnEvent]:
        return _stream_turn(
            self._client,
            model=model,
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
        )

    def tool_turn(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 4000,
    ) -> ToolTurn:
        started = time.perf_counter()
        try:
            params: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "system": [
                    {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                ],
                "messages": messages,
                "tools": tools,
                "output_config": {"effort": "medium"},
            }
            response = self._client.messages.create(**params)
        except anthropic.APIError as exc:
            raise LlmUnavailableError(str(exc)) from exc
        content = [block.to_dict() for block in response.content]
        return ToolTurn(
            content=content,
            stop_reason=response.stop_reason,
            usage=_usage(model, response.usage, started),
            text="".join(b.get("text", "") for b in content if b.get("type") == "text"),
            tool_calls=[b for b in content if b.get("type") == "tool_use"],
        )


def _stream_turn(
    client: anthropic.Anthropic,
    *,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_tokens: int,
) -> Iterator[TurnEvent]:
    started = time.perf_counter()
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": messages,
        "tools": tools,
        "cache_control": {"type": "ephemeral"},
        "output_config": {"effort": "medium"},
    }
    block_types: dict[int, str] = {}
    try:
        with client.messages.stream(**params) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    block_types[event.index] = event.content_block.type
                    if event.content_block.type == "tool_use":
                        yield ToolStart(event.content_block.name)
                elif event.type == "content_block_stop":
                    if block_types.get(event.index) == "text":
                        yield BlockEnd()
                elif event.type == "content_block_delta":
                    if event.delta.type == "text_delta":
                        yield TextDelta(event.delta.text)
                    elif event.delta.type == "citations_delta":
                        c = event.delta.citation
                        if isinstance(c, CitationsSearchResultLocation):
                            yield Citation(
                                search_result_index=c.search_result_index,
                                start_block_index=c.start_block_index,
                                end_block_index=c.end_block_index,
                                cited_text=c.cited_text,
                            )
            final = stream.get_final_message()
    except anthropic.APIError as exc:
        raise LlmUnavailableError(str(exc)) from exc
    yield TurnEnd(
        content=[block.to_dict() for block in final.content],
        stop_reason=final.stop_reason,
        usage=_usage(model, final.usage, started),
    )
