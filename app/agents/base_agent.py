import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import anthropic

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Generic async agent loop built on the Anthropic API with tool use.

    Subclass this and implement `execute_tool` to add domain-specific logic.
    Conversation history is maintained across multiple `run()` calls.

    G3 gate
    -------
    Pass `g3_gates={"tool_to_protect": "required_prerequisite_tool"}` to enforce
    that a tool cannot be called until its prerequisite has been called in the
    same turn.  The gate fires before `execute_tool` is reached, so the booking
    can never happen without a prior slot check.

    Example:
        g3_gates={"agendar_consulta": "verificar_slots"}

    When triggered:
      - Returns a structured error tool_result to the model.
      - The model naturally corrects itself by calling the prerequisite first.
      - Calls `_on_g3_violation()` for audit/logging (override in subclasses).
    """

    DEFAULT_MODEL = "claude-opus-4-6"
    DEFAULT_MAX_TOKENS = 16000
    DEFAULT_MAX_ITERATIONS = 10

    def __init__(
        self,
        system_prompt: str,
        tools: list[dict],
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        g3_gates: dict[str, str] | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.tools = tools
        self.model = model
        self.max_tokens = max(max_tokens, 16000)
        self.max_iterations = max_iterations
        self._thinking: dict = {"type": "adaptive"}
        self.g3_gates: dict[str, str] = g3_gates or {}

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._history: list[dict] = []
        self._turn_count: int = 0
        self._tools_called_this_turn: set[str] = set()
        self._last_run_input_tokens: int = 0   # accumulated per run() call
        self._last_run_output_tokens: int = 0

    # ─── Public API ───────────────────────────────────────────────────────────

    async def run(self, user_input: str, *, extra_system: str = "") -> str:
        """
        Send a user message and run the agentic loop until a final response.
        Conversation history is preserved between calls.

        extra_system: optional block appended to the system prompt for this
        call only (e.g. a context_snapshot injected by the caller).
        """
        self._turn_count += 1
        self._tools_called_this_turn = set()   # reset per turn
        self._last_run_input_tokens  = 0       # reset per run()
        self._last_run_output_tokens = 0

        self._history.append({"role": "user", "content": user_input})

        effective_system = (
            self.system_prompt + "\n\n" + extra_system
            if extra_system
            else self.system_prompt
        )

        for iteration in range(self.max_iterations):
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking=self._thinking,
                system=effective_system,
                tools=self.tools,
                messages=self._history,
            )

            logger.debug(
                "Iteration %d/%d — stop_reason=%s",
                iteration + 1,
                self.max_iterations,
                response.stop_reason,
            )

            # Accumulate token usage for cost tracking
            if hasattr(response, "usage") and response.usage:
                self._last_run_input_tokens  += getattr(response.usage, "input_tokens",  0) or 0
                self._last_run_output_tokens += getattr(response.usage, "output_tokens", 0) or 0

            # Always append the full content (preserves thinking blocks)
            self._history.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                return self._extract_text(response.content)

            if response.stop_reason != "tool_use":
                logger.warning("Unexpected stop_reason: %s", response.stop_reason)
                break

            tool_results = await self._run_tool_calls(response.content)
            self._history.append({"role": "user", "content": tool_results})

        logger.error("Agent reached max_iterations (%d) without end_turn.", self.max_iterations)
        raise RuntimeError(
            f"Agent exceeded max_iterations ({self.max_iterations}) without producing a final response."
        )

    def reset_history(self) -> None:
        """Clear conversation history to start a fresh session."""
        self._history.clear()

    # ─── Tool execution ───────────────────────────────────────────────────────

    @abstractmethod
    async def execute_tool(self, tool_name: str, tool_input: dict) -> Any:
        """
        Execute a tool and return its result.

        Return value can be a string, dict, or list — the agent converts it
        to a string automatically. Raise an exception on failure; the agent
        will catch it and report the error back to the model.
        """

    # ─── G3 gate hook ─────────────────────────────────────────────────────────

    async def _on_g3_violation(self, attempted_tool: str, required_tool: str) -> None:
        """
        Called when the G3 gate blocks a tool call.
        Default: log a warning. Override in subclasses to add audit DB inserts.
        """
        logger.warning(
            "G3 gate triggered | turn=%d attempted='%s' required='%s'",
            self._turn_count,
            attempted_tool,
            required_tool,
        )

    # ─── Internals ────────────────────────────────────────────────────────────

    async def _run_tool_calls(self, content: list) -> list[dict]:
        """Execute every tool_use block in the response, enforcing G3 gates."""
        results = []
        for block in content:
            if not hasattr(block, "type") or block.type != "tool_use":
                continue

            # ── G3 gate check ─────────────────────────────────────────────────
            required = self.g3_gates.get(block.name)
            if required and required not in self._tools_called_this_turn:
                await self._on_g3_violation(block.name, required)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps({
                        "error": "G3_VIOLATION",
                        "message": (
                            f"Preciso verificar os horários disponíveis primeiro. "
                            f"Usa '{required}' antes de tentar '{block.name}'."
                        ),
                    }, ensure_ascii=False),
                    "is_error": True,
                })
                continue

            # ── Track as called (only after gate passes) ───────────────────────
            self._tools_called_this_turn.add(block.name)
            logger.debug("Calling tool '%s' with input: %s", block.name, block.input)

            # ── Execute ────────────────────────────────────────────────────────
            try:
                raw = await self.execute_tool(block.name, block.input)
                result_content = self._coerce_to_str(raw)
                is_error = False
            except Exception as exc:
                result_content = f"Tool '{block.name}' failed: {exc}"
                is_error = True
                logger.exception("Tool '%s' raised an exception", block.name)

            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_content,
                **({"is_error": True} if is_error else {}),
            })

        return results

    @staticmethod
    def _extract_text(content: list) -> str:
        for block in content:
            if hasattr(block, "type") and block.type == "text":
                return block.text
        return ""

    @staticmethod
    def _coerce_to_str(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)
