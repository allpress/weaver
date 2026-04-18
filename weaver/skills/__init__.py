"""Skills: swappable capabilities with a consistent `execute(action, **kwargs)` interface."""
from weaver.skills.base import Skill, SkillManifest, SkillResult
from weaver.skills.registry import SkillRegistry, get_registry

__all__ = ["Skill", "SkillManifest", "SkillResult", "SkillRegistry", "get_registry"]
