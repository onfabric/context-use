from __future__ import annotations

from context_use.agent.runner import AgentResult, _render_system_prompt


class TestAgentResult:
    def test_summary_field(self) -> None:
        result = AgentResult(summary="Created 3 memories")
        assert result.summary == "Created 3 memories"


class TestRenderSystemPrompt:
    def test_contains_current_time(self) -> None:
        prompt = _render_system_prompt(None)
        assert "Current time:" in prompt

    def test_contains_tool_descriptions(self) -> None:
        prompt = _render_system_prompt(None)
        assert "list_memories" in prompt
        assert "search_memories" in prompt
        assert "create_memory" in prompt
