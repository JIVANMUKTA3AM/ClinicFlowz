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
    """

    DEFAULT_MODEL = "claude-opus-4-6"
    DEFAULT_MAX_TOKENS = 4096
    DEFAULT_MAX_ITERATIONS = 10
    DEFAULT_THINKING_BUDGET = 1024

    def __init__(
        self,
        system_prompt: str,
        tools: list[dict],
        *,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        thinking_budget: int | None = DEFAULT_THINKING_BUDGET,
    ) -> None:
        self.system_prompt = system_prompt
        self.tools = tools
        self.model = model
        self.max_tokens = max_tokens
        self.max_iterations = max_iterations
        self._thinking: dict = (
            {"type": "enabled", "budget_tokens": thinking_budget}
            if thinking_budget is not None
            else {"type": "disabled"}
        )

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._history: list[dict] = []

    # ─── Public API ───────────────────────────────────────────────────────────

    async def run(self, user_input: str) -> str:
        """
        Send a user message and run the agentic loop until a final response.
        Conversation history is preserved between calls.
        """
        self._history.append({"role": "user", "content": user_input})

        for iteration in range(self.max_iterations):
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                thinking=self._thinking,
                system=self.system_prompt,
                tools=self.tools,
                messages=self._history,
            )

            logger.debug(
                "Iteration %d/%d — stop_reason=%s",
                iteration + 1,
                self.max_iterations,
                response.stop_reason,
            )

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

    # ─── Internals ────────────────────────────────────────────────────────────

    async def _run_tool_calls(self, content: list) -> list[dict]:
        """Execute every tool_use block in the response and collect results."""
        results = []
        for block in content:
            if not hasattr(block, "type") or block.type != "tool_use":
                continue

            logger.debug("Calling tool '%s' with input: %s", block.name, block.input)

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
            import json
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)
