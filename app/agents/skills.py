"""Teaching skill loader.

A skill is a teaching-strategy document that supplements an agent's behaviour.
Keeping them as files means the explanation structure, question-writing standard
and grading boundaries can be reviewed and edited without touching Python.
"""

from dataclasses import dataclass, field
from functools import lru_cache
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#: A turn injects at most this many skills, so the system prompt stays focused.
MAX_INJECTED_SKILLS = 2


@dataclass(frozen=True)
class TeachingSkill:
    name: str
    description: str
    content: str
    keywords: tuple[str, ...] = ()
    agents: tuple[str, ...] = ()
    enabled: bool = True

    def matches(self, message: str, agent: str) -> bool:
        """Empty `agents` means every agent; empty `keywords` means always on."""

        if not self.enabled:
            return False
        if self.agents and agent.casefold() not in self.agents:
            return False
        if not self.keywords:
            return True
        return any(term in message for term in self.keywords)


class TeachingSkillLibrary:
    def __init__(self, skills: list[TeachingSkill]) -> None:
        self.skills = skills

    def select(self, *, message: str, agent: str) -> list[TeachingSkill]:
        normalized = " ".join(message.casefold().split())
        matched = [skill for skill in self.skills if skill.matches(normalized, agent)]
        # Keyword hits are more specific than always-on skills, so rank them first.
        matched.sort(key=lambda skill: (not skill.keywords, skill.name))
        return matched[:MAX_INJECTED_SKILLS]

    def prompt_section(self, *, message: str, agent: str) -> str:
        selected = self.select(message=message, agent=agent)
        if not selected:
            return ""
        blocks = "\n\n".join(f"## {skill.name}\n{skill.content}" for skill in selected)
        return f"# Teaching guidance\n\n{blocks}"


def load_skills(directory: Path) -> list[TeachingSkill]:
    if not directory.is_dir():
        logger.warning("skills directory not found: %s", directory)
        return []
    skills: list[TeachingSkill] = []
    for path in sorted(directory.glob("*/SKILL.md")):
        skill = _parse(path)
        if skill is not None:
            skills.append(skill)
    return skills


def _parse(path: Path) -> TeachingSkill | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("could not read skill: %s", path)
        return None
    metadata, content = _split_frontmatter(raw)
    name = metadata.get("name") or path.parent.name
    if not content.strip():
        logger.warning("skill has no content: %s", path)
        return None
    return TeachingSkill(
        name=name,
        description=metadata.get("description", ""),
        content=content.strip(),
        keywords=_csv(metadata.get("keywords")),
        agents=_csv(metadata.get("agents")),
        enabled=metadata.get("enabled", "true").strip().casefold() != "false",
    )


def _split_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()
    return metadata, parts[2]


def _csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip().casefold() for item in value.split(",") if item.strip())


@lru_cache(maxsize=1)
def get_skill_library() -> TeachingSkillLibrary:
    directory = Path(__file__).resolve().parents[2] / "skills"
    skills = load_skills(directory)
    logger.info("loaded %d teaching skill(s)", len(skills))
    return TeachingSkillLibrary(skills)
