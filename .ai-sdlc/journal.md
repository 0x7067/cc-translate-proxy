## 2026-07-03 — Configurable language pair for English-visible mode
- Did: added `CC_I18N_USER_LANG` and `CC_I18N_CLAUDE_LANG`, wired them through request translation, assistant render/audit translation, retry translation, language-pair-aware cache keys, translator prompt guidance, README docs, and focused tests for `en` to `zh-Hans` to `en`.
- Verified: `uv run pytest tests/test_pipeline.py tests/test_server_smoke.py -v` passed 12 tests; `uv run pytest tests/test_retry_endpoint.py tests/test_translator_prompt.py -v` passed 10 tests; `uv run pytest -v` passed 209 tests; `uv run ruff check .` printed `All checks passed!`; `git diff --check` passed with no output; `check-state.sh` printed `check-state: OK`.
- Learned: the proxy still returns upstream Claude bytes to Claude Code and writes translated assistant text to audit/render; for non-default modes the old `user_zh` and `assistant_zh` field names now mean visible-side text, not necessarily Chinese.
- Left: optional live provider smoke for `CC_I18N_USER_LANG=en` / `CC_I18N_CLAUDE_LANG=zh-Hans`, and a possible backward-compatible audit/render field rename.

## 2026-07-03 — Rewrite Claude Code TUI responses for reverse mode
- Did: added `CC_I18N_REWRITE_TUI` with auto-on behavior for non-English Claude-facing modes, rewrote JSON and SSE assistant responses back to user language before returning to Claude Code, reused that translation for audit/render, and translated assistant-history text back into Claude language on outbound requests.
- Verified: `uv run pytest tests/test_server_smoke.py -v` passed 7 tests; `uv run pytest tests/test_pipeline.py tests/test_config.py -v` passed 10 tests after creating `tests/test_config.py`; `uv run pytest -v` passed 214 tests; `uv run ruff check .` printed `All checks passed!`; `git diff --check` passed with no output.
- Learned: the proxy already buffers upstream responses before returning them, so response rewriting preserves the existing non-streaming behavior while changing the bytes Claude Code receives.
- Left: optional live provider smoke for the reverse mode; exact tool/system surfaces remain intentionally untranslated.

## 2026-07-03 — Add one-command reverse-mode launcher
- Did: added `scripts/claude-english.sh` to set reverse-mode env, start proxy and render server, launch `claude`, and clean up child processes on exit; README now points to this as the simplest run path.
- Verified: `bash -n scripts/claude-english.sh` passed; `uv run pytest -v` passed 214 tests; `uv run ruff check .` printed `All checks passed!`; `git diff --check` passed with no output; `check-state.sh` printed `check-state: OK`.
- Learned: the launcher should fail when proxy/render ports are already in use rather than silently reusing a possibly wrong-mode daemon.
- Left: optional live smoke with the launcher against real provider credentials.

## 2026-07-03 — Remove `/intl` requirement from reverse-mode launcher
- Did: added `CC_I18N_AUTO_TRANSLATE`, set it in `scripts/claude-english.sh`, updated README, and proved reverse mode translates a request with no marker or `/intl` command.
- Verified: `uv run pytest tests/test_config.py tests/test_server_smoke.py -v` passed 12 tests; `bash -n scripts/claude-english.sh` passed; `git diff --check` passed with no output; `uv run pytest -v` passed 216 tests; `uv run ruff check .` printed `All checks passed!`; `check-state.sh` printed `check-state: OK`.
- Learned: marker-based translation remains available for manual/default proxy runs, but the reverse-mode launcher now opts every proxied request into translation.
- Left: optional live launcher smoke with an OpenRouter key present in `~/.cc-i18n-proxy/.env`.

## 2026-07-03 — Add launchd background proxy workflow
- Did: added `scripts/proxy-background.sh` to install/start/stop/status macOS user LaunchAgents for the proxy and render server, defaulting to English-visible / Simplified-Chinese-upstream reverse mode with auto-translate enabled; updated README quick start so future Claude Code shells only need `export ANTHROPIC_BASE_URL=http://localhost:8080`.
- Verified: `bash -n scripts/proxy-background.sh` passed; `./scripts/proxy-background.sh start` printed started proxy/render services; escalated `./scripts/proxy-background.sh status` printed both jobs loaded and ports 8080/9090 open; escalated `curl` to `http://127.0.0.1:8080/docs` and `http://127.0.0.1:9090/` returned 200; `plutil -lint` printed both LaunchAgent plists OK; focused pytest passed 12 tests before the edit and will be rerun in final validation.
- Learned: sandbox-local port checks can report launchd services as closed even when they are reachable outside the sandbox, so live background verification needs an unsandboxed localhost probe. The user also explicitly said not to worry about backward compatibility for future migrations.
- Left: optional live Claude Code smoke through the background proxy with real provider credentials.

## 2026-07-03 — Make render opt-in for background workflow
- Did: changed `scripts/proxy-background.sh start` to install/start only the proxy LaunchAgent and stop any existing render LaunchAgent from the earlier workflow; added explicit `start-render`, `stop-render`, and `start-all` commands; updated README and state so the default user flow only requires `ANTHROPIC_BASE_URL`.
- Verified: `bash -n scripts/proxy-background.sh` passed; `./scripts/proxy-background.sh --help` showed proxy-only `start` plus explicit render commands; `./scripts/proxy-background.sh start` left proxy loaded/open and render not loaded/closed; `start-render` and `start-all` opened render on 9090; `stop-render` returned the machine to proxy-only; `uv run pytest -v` passed 216 tests; `uv run ruff check .` printed `All checks passed!`.
- Learned: render is not needed for the "just export ANTHROPIC_BASE_URL" workflow and should not run by default.
- Left: optional live Claude Code smoke through the proxy-only background service.

## 2026-07-03 — Add chinese-claude launcher wrapper
- Did: added executable `chinese-claude`, which checks that the local proxy is reachable, sets `ANTHROPIC_BASE_URL=http://localhost:8080` and `ENABLE_TOOL_SEARCH=auto` by default, then execs `claude`; installed `~/.local/bin/chinese-claude` as a symlink to it; updated README and state to make the wrapper the normal launch path.
- Verified: `bash -n chinese-claude` passed; `chinese-claude --print-env --help` printed the expected env and argv; a stale `ANTHROPIC_BASE_URL` override was ignored in favor of `http://localhost:8080`; `CC_I18N_PROXY_PORT=65534 chinese-claude --print-env` failed clearly; `uv run pytest tests/test_config.py tests/test_server_smoke.py -v` passed 12 tests; `uv run ruff check .` printed `All checks passed!`; `git diff --check` passed; `check-state.sh` printed `check-state: OK`.
- Learned: keep this wrapper as a launcher only; proxy lifetime remains owned by `scripts/proxy-background.sh`.
- Left: optional live interactive Claude Code smoke through `chinese-claude`.
