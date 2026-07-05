"""Environment-based configuration."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    listen_port: int
    anthropic_upstream: str
    home: Path
    cache_db_path: Path
    audit_log_dir: Path
    emit_file_dir: Path
    log_protocol_observations: bool
    protocol_observations_path: Path
    user_lang: str
    claude_lang: str
    rewrite_tui_response: bool
    auto_translate: bool

    @classmethod
    def from_env(cls) -> "Config":
        home = Path(os.environ.get("CC_I18N_PROXY_HOME", Path.home() / ".cc-i18n-proxy"))
        home.mkdir(mode=0o700, parents=True, exist_ok=True)
        (home / "audit").mkdir(mode=0o700, exist_ok=True)
        emit_file_dir = Path(os.environ.get("CC_I18N_PROXY_EMIT_DIR", home / "emit"))
        emit_file_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        user_lang = _env_lang("CC_I18N_USER_LANG", "zh")
        claude_lang = _env_lang("CC_I18N_CLAUDE_LANG", "en")
        return cls(
            listen_port=int(os.environ.get("CC_I18N_PROXY_PORT", "8080")),
            anthropic_upstream=os.environ.get("ANTHROPIC_UPSTREAM", "https://api.anthropic.com"),
            home=home,
            cache_db_path=home / "cache.db",
            audit_log_dir=home / "audit",
            emit_file_dir=emit_file_dir,
            log_protocol_observations=os.environ.get("CC_I18N_PROXY_LOG_PROTOCOL", "0") == "1",
            protocol_observations_path=home / "protocol-observations.md",
            user_lang=user_lang,
            claude_lang=claude_lang,
            rewrite_tui_response=_env_bool(
                "CC_I18N_REWRITE_TUI",
                default=claude_lang != "en",
            ),
            auto_translate=_env_bool("CC_I18N_AUTO_TRANSLATE", default=False),
        )


def _env_lang(name: str, default: str) -> str:
    value = os.environ.get(name, default).strip()
    return value or default


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
