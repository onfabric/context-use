from __future__ import annotations

from context_use.agent.skill import make_process_thread_skill


class TestMakeProcessThreadSkill:
    def test_transcript_injected_into_prompt(self) -> None:
        transcript = "## Transcript\n\n[ME 2025-06-15 10:30] Hello"
        skill = make_process_thread_skill(transcript)

        assert skill.name == "process_thread"
        assert transcript in skill.prompt
        assert "search_memories" in skill.prompt

    def test_prompt_contains_instructions(self) -> None:
        skill = make_process_thread_skill("some transcript")

        assert "create_memory" in skill.prompt
        assert "update_memory" in skill.prompt
        assert "What to capture" in skill.prompt
