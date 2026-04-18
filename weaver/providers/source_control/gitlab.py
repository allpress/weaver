"""GitLab source-control provider."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from weaver.providers.base import ProviderCapability, Record
from weaver.providers.source_control.base import CloneResult, SourceControl

log = logging.getLogger(__name__)


class GitLabProvider(SourceControl):
    name = "gitlab"

    def __init__(self, *, base_url: str, token: str | None = None,
                 oauth_bearer: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._bearer = oauth_bearer
        self._client: Any | None = None

    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.read,
            ProviderCapability.api_token,
            ProviderCapability.oauth,
        }

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import gitlab
        except ImportError as e:
            raise RuntimeError("python-gitlab required: pip install python-gitlab") from e

        kwargs: dict[str, Any] = {"url": self._base_url}
        if self._token:
            kwargs["private_token"] = self._token
        elif self._bearer:
            kwargs["oauth_token"] = self._bearer
        self._client = gitlab.Gitlab(**kwargs)
        self._client.auth()
        return self._client

    def list_projects(self, *, group: str | None = None, **_: Any) -> Iterable[Record]:
        client = self._get_client()
        if group:
            grp = client.groups.get(group)
            projects = grp.projects.list(include_subgroups=True, all=True, iterator=True)
        else:
            projects = client.projects.list(membership=True, all=True, iterator=True)

        for p in projects:
            yield Record(
                id=str(p.id),
                type="gitlab_project",
                source_uri=p.web_url,
                payload={
                    "name": p.name,
                    "path_with_namespace": p.path_with_namespace,
                    "default_branch": getattr(p, "default_branch", "main") or "main",
                    "http_url_to_repo": p.http_url_to_repo,
                    "ssh_url_to_repo": p.ssh_url_to_repo,
                    "description": p.description or "",
                    "visibility": p.visibility,
                    "archived": bool(getattr(p, "archived", False)),
                },
            )

    def fetch(self, **query: Any) -> Iterable[Record]:
        return self.list_projects(**query)

    def clone_into(self, project: Record, dest_root: Path, *,
                   protocol: str = "https") -> CloneResult:
        try:
            import git as gitpy
        except ImportError as e:
            raise RuntimeError("GitPython required") from e

        slug = project.payload["path_with_namespace"].replace("/", "__")
        dest = dest_root / slug
        default_branch = project.payload.get("default_branch") or "main"

        if protocol == "ssh":
            url = project.payload["ssh_url_to_repo"]
        else:
            url = self._authed_https(project.payload["http_url_to_repo"])

        if (dest / ".git").exists():
            log.info("already present, pulling: %s", slug)
            repo = gitpy.Repo(dest)
            try:
                repo.remotes.origin.pull()
            except Exception as e:  # noqa: BLE001
                log.warning("pull failed for %s: %s", slug, e)
            cloned = False
        else:
            log.info("cloning %s -> %s", url, dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            gitpy.Repo.clone_from(url, dest, depth=1)
            cloned = True

        size_kb = _tree_size_kb(dest)
        languages = _simple_lang_census(dest)

        return CloneResult(
            name=slug,
            path=dest,
            http_url=project.source_uri,
            default_branch=default_branch,
            size_kb=size_kb,
            languages=languages,
            cloned=cloned,
        )

    def _authed_https(self, url: str) -> str:
        """Inject the token into the HTTPS URL for non-interactive clones."""
        if not self._token:
            return url
        # https://gitlab.example.com/group/proj.git -> https://oauth2:TOKEN@…
        if url.startswith("https://"):
            rest = url[len("https://"):]
            return f"https://oauth2:{self._token}@{rest}"
        return url


def _tree_size_kb(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total // 1024


def _simple_lang_census(path: Path) -> dict[str, int]:
    """Rough per-language byte count. No external deps."""
    from weaver.parsers.code_parser import _EXT_LANG
    tally: dict[str, int] = {}
    for p in path.rglob("*"):
        if not p.is_file() or ".git" in p.parts:
            continue
        lang = _EXT_LANG.get(p.suffix.lower())
        if lang is None:
            continue
        try:
            tally[lang] = tally.get(lang, 0) + p.stat().st_size
        except OSError:
            continue
    return tally
