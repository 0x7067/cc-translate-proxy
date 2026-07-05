# Project State
updated: 2026-07-03

## Goal
cc-translate-proxy is a sidecar proxy for Claude Code that translates the user-facing
conversation separately from the Anthropic-facing conversation. It currently targets
Traditional Chinese user text and English upstream Claude traffic, with local audit and
render artifacts for translated turns.

## Now
English-visible / Simplified-Chinese-upstream mode is implemented for both render and
Claude Code TUI responses. `scripts/proxy-background.sh start` installs macOS user
LaunchAgent that keeps only the proxy running in reverse mode, so new Claude Code
shells only need `export ANTHROPIC_BASE_URL=http://localhost:8080`. Render web UI is
opt-in via `scripts/proxy-background.sh start-render`.
The `chinese-claude` wrapper launches Claude Code against the running proxy without
manual env setup.
Defaults remain Traditional Chinese user/render text with English Claude-facing traffic
when the proxy is started manually without reverse-mode env.

## Verification path
- `uv run pytest -v` passed 216 tests on 2026-07-03.
- `uv run pytest tests/test_config.py tests/test_server_smoke.py -v` passed 12 tests on 2026-07-03.
- `uv run ruff check .` passed on 2026-07-03.
- `git diff --check` passed on 2026-07-03.
- `bash -n scripts/claude-english.sh` passed on 2026-07-03.
- `bash -n scripts/proxy-background.sh` passed on 2026-07-03.
- `bash -n chinese-claude` passed on 2026-07-03.
- `./scripts/proxy-background.sh start` passed on 2026-07-03 and opened `127.0.0.1:8080` while leaving render unloaded.
- `bash ~/.agents/skills/sdlc-core/scripts/check-state.sh` passed on 2026-07-03.

## Decisions
- Preserve the default README behavior unless explicitly changed: existing users expect
  Traditional Chinese input, English upstream, and Traditional Chinese render output.
- Route translation through provider chains rather than one-off provider calls so failover,
  audit, retry, and render UI behavior stays consistent.
- Configure alternate language pairs with `CC_I18N_USER_LANG` and `CC_I18N_CLAUDE_LANG`
  instead of hard-coding a second mode; this keeps future pairs testable through the same path.
- `CC_I18N_REWRITE_TUI` defaults on when `CC_I18N_CLAUDE_LANG` is not `en`, so reverse
  mode returns English to Claude Code and translates assistant history back to Claude language.
- `scripts/claude-english.sh` owns starting/stopping proxy and render child processes for
  reverse mode; manual env setup remains documented for debugging.
- `CC_I18N_AUTO_TRANSLATE=1` skips the old `/intl` marker requirement; the reverse-mode
  launcher enables it by default.
- `scripts/proxy-background.sh` uses launchd user agents for the durable background flow
  on macOS; `start` is proxy-only, and render is opt-in with `start-render`.
- `chinese-claude` is the user-facing launcher for proxied Claude Code sessions; it sets
  `ANTHROPIC_BASE_URL` and `ENABLE_TOOL_SEARCH` but does not start the proxy itself.
- Future schema/field migrations do not need backward-compatible handling when the simpler
  breaking change is cleaner; the user explicitly accepted that tradeoff on 2026-07-03.

## Landmines
- `uv run pytest -v` may need access to the shared uv cache outside the workspace sandbox.
- Sandbox-local HTTP probes can report localhost ports closed even while launchd services
  are reachable; verify background services outside the sandbox when checking live ports.
- Translation cache keys are language-pair-aware as of 2026-07-03; avoid regressing to
  text-only keys if more language modes are added.
- System prompts, tool definitions, tool_use, and tool_result blocks are intentionally not
  translated; translating them risks breaking Claude Code tool semantics and exact outputs.

## Next
1. If desired, run a live Claude Code smoke with `export ANTHROPIC_BASE_URL=http://localhost:8080`;
   done when the TUI returns English, proxy logs show `/v1/messages`, and audit output shows
   Simplified Chinese Claude-facing user/assistant history without using `/intl`.
2. Consider renaming audit/render field names such as `user_zh` and `assistant_zh` in
   `src/cc_i18n_proxy/audit.py`, `server.py`, and render tests without preserving old
   JSONL compatibility; done when new JSONL exposes generic field names and tests pass.
