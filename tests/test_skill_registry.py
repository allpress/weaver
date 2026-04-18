from __future__ import annotations

from typing import Any

from weaver.skills import Skill, SkillManifest, SkillResult, SkillRegistry


class _Echo(Skill):
    manifest = SkillManifest(
        name="echo", kind="domain", version="0.1.0",
        actions=["say"], description="echo",
    )

    def execute(self, action: str, **kwargs: Any) -> SkillResult:
        if action != "say":
            return SkillResult(ok=False, error="unknown action")
        return SkillResult(ok=True, data=kwargs.get("msg", ""))


def test_registry_execute() -> None:
    reg = SkillRegistry()
    reg.register(_Echo())
    assert "echo" in reg.list()
    result = reg.execute("echo", "say", msg="hi")
    assert result.ok and result.data == "hi"


def test_unknown_action() -> None:
    reg = SkillRegistry()
    reg.register(_Echo())
    result = reg.execute("echo", "nope")
    assert not result.ok
