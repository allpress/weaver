"""Config loading. Reads _config/defaults.ini (or template fallback) + context INI."""
from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path

from weaver.paths import (
    config_dir,
    context_config_path,
    contexts_root,
    repo_root,
)


@dataclass(slots=True)
class GlobalConfig:
    default_context: str
    parallel_workers: int
    cache_freshness_hours: int
    contexts_root: Path
    proxy_cert_path: Path | None
    secrets_backend: str
    encrypted_file_path: Path
    parser_timeout_s: int
    parser_max_bytes: int
    rag_embedding_backend: str
    rag_embedding_model: str
    rag_chunk_size: int
    rag_chunk_overlap: int
    rag_top_k: int
    graph_languages: list[str]
    graph_max_file_bytes: int
    auth_strict_precedence: bool
    auth_allow_playwright_in_ci: bool
    raw: configparser.ConfigParser = field(default_factory=configparser.ConfigParser)


@dataclass(slots=True)
class ContextConfig:
    name: str
    display_name: str
    active: bool
    source_control_provider: str | None
    source_control_base_url: str | None
    source_control_group: str | None
    source_control_clone_protocol: str
    playwright_allowed: dict[str, bool]       # provider -> allowed
    playwright_reasons: dict[str, str]
    raw: configparser.ConfigParser = field(default_factory=configparser.ConfigParser)


def _read_ini(path: Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None)
    if path.exists():
        cp.read(path, encoding="utf-8")
    return cp


def _get(cp: configparser.ConfigParser, section: str, key: str, default: str = "") -> str:
    if cp.has_section(section) and cp.has_option(section, key):
        return cp.get(section, key).strip()
    return default


def _get_bool(cp: configparser.ConfigParser, section: str, key: str, default: bool) -> bool:
    v = _get(cp, section, key)
    if not v:
        return default
    return v.lower() in {"1", "true", "yes", "on"}


def _get_int(cp: configparser.ConfigParser, section: str, key: str, default: int) -> int:
    v = _get(cp, section, key)
    return int(v) if v else default


def load_global() -> GlobalConfig:
    """Load global config. Falls back to defaults.ini.template if user hasn't run setup."""
    primary = config_dir() / "defaults.ini"
    fallback = config_dir() / "defaults.ini.template"
    cp = _read_ini(primary if primary.exists() else fallback)

    root = repo_root()
    contexts = _get(cp, "paths", "contexts_root", "contexts")
    cert = _get(cp, "paths", "proxy_cert_path", "") or None

    return GlobalConfig(
        default_context=_get(cp, "general", "default_context", "default"),
        parallel_workers=_get_int(cp, "general", "parallel_workers", 4),
        cache_freshness_hours=_get_int(cp, "general", "cache_freshness_hours", 24),
        contexts_root=(root / contexts).resolve(),
        proxy_cert_path=Path(cert).resolve() if cert else None,
        secrets_backend=_get(cp, "secrets", "backend", "auto"),
        encrypted_file_path=(root / _get(cp, "secrets", "encrypted_file_path",
                                         "_config/.secrets.enc")).resolve(),
        parser_timeout_s=_get_int(cp, "parsers", "timeout_s", 30),
        parser_max_bytes=_get_int(cp, "parsers", "max_bytes", 50_000_000),
        rag_embedding_backend=_get(cp, "rag", "embedding_backend", "sentence-transformers"),
        rag_embedding_model=_get(cp, "rag", "embedding_model", "all-MiniLM-L6-v2"),
        rag_chunk_size=_get_int(cp, "rag", "chunk_size", 800),
        rag_chunk_overlap=_get_int(cp, "rag", "chunk_overlap", 120),
        rag_top_k=_get_int(cp, "rag", "top_k", 8),
        graph_languages=[
            s.strip() for s in _get(
                cp, "graph", "languages",
                "python,typescript,javascript,go,rust,java,ruby,c,cpp",
            ).split(",") if s.strip()
        ],
        graph_max_file_bytes=_get_int(cp, "graph", "max_file_bytes", 2_000_000),
        auth_strict_precedence=_get_bool(cp, "auth", "strict_precedence", True),
        auth_allow_playwright_in_ci=_get_bool(cp, "auth", "allow_playwright_in_ci", False),
        raw=cp,
    )


def load_context(name: str) -> ContextConfig:
    path = context_config_path(name)
    if not path.exists():
        raise FileNotFoundError(
            f"Context '{name}' does not exist at {path}. "
            f"Create it with: weaver context create {name}"
        )
    cp = _read_ini(path)

    playwright_allowed: dict[str, bool] = {}
    playwright_reasons: dict[str, str] = {}
    for section in cp.sections():
        if section.startswith("auth.providers."):
            provider = section.split(".", 2)[2]
            playwright_allowed[provider] = _get_bool(cp, section, "allow_playwright_scrape", False)
            reason = _get(cp, section, "playwright_scrape_reason")
            if reason:
                playwright_reasons[provider] = reason

    return ContextConfig(
        name=name,
        display_name=_get(cp, "context", "display_name", name),
        active=_get_bool(cp, "context", "active", False),
        source_control_provider=_get(cp, "sources", "source_control") or None,
        source_control_base_url=_get(cp, "source_control", "base_url") or None,
        source_control_group=_get(cp, "source_control", "group_or_owner") or None,
        source_control_clone_protocol=_get(cp, "source_control", "clone_protocol", "https"),
        playwright_allowed=playwright_allowed,
        playwright_reasons=playwright_reasons,
        raw=cp,
    )


def list_contexts() -> list[str]:
    root = contexts_root()
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "context.ini").exists())
