
from dataclasses import dataclass
from pathlib import Path

_SKILLS_DIR = Path(__file__).parent / "skills"


@dataclass(frozen=True)
class AgentSkill:
    """A named task that can be sent to the personal agent as a user message."""

    name: str
    description: str
    prompt: str


def _load(filename: str) -> str:
    return (_SKILLS_DIR / filename).read_text(encoding="utf-8")


BUILT_IN_SKILLS: dict[str, AgentSkill] = {
    "synthesise": AgentSkill(
        name="synthesise",
        description=(
            "Investigate the memory store topic by topic and synthesise "
            "higher-level pattern memories."
        ),
        prompt=_load("synthesise.md"),
    ),
    "profile": AgentSkill(
        name="profile",
        description=(
            "Survey the entire memory store and compile a structured "
            "first-person user profile in Markdown. Printed to stdout. "
            "Read-only."
        ),
        prompt=_load("user_profile.md"),
    ),
}


def get_skill(name: str) -> AgentSkill:
    """Return a built-in skill by name, or raise :exc:`KeyError`."""
    return BUILT_IN_SKILLS[name]


def list_skills() -> list[AgentSkill]:
    """Return all built-in skills in definition order."""
    return list(BUILT_IN_SKILLS.values())


def make_adhoc_skill(prompt: str) -> AgentSkill:
    """Wrap a free-form user query as a one-off skill."""
    return AgentSkill(name="adhoc", description="User-supplied query", prompt=prompt)
