# cc-translate-proxy

讓 [Claude Code](https://claude.com/claude-code) 的本機介面語言跟送進 Claude 的語言分開的 sidecar 翻譯 proxy。

公開 repo：https://github.com/0x7067/cc-translate-proxy

目前有兩種常用跑法：

- `chinese-claude`：你在 Claude Code 裡用英文讀寫；Claude-facing 的 user / assistant history 是簡中；不需要 `/intl`。
- 手動 `/intl`：你用繁中 prompt；proxy 送英文給 Claude，英文回覆留給 Claude Code，繁中 render 另外顯示在本機網頁。

![cc-translate-proxy demo — 一段對話，兩種語言](screenshots/brag-demo.gif)

## 為什麼做這個

核心問題是：Claude Code 本機看到的語言，不一定要跟模型上下文裡的語言綁在一起。最早的動機來自繁中使用者想把 Claude-facing context 維持在英文；後來也加了英文介面、簡中 upstream 的反向模式。

兩件事讓我覺得值得寫個 sidecar：

1. **Claude Code 用英文比中文穩**。Anthropic 自家 [multilingual benchmark](https://platform.claude.com/docs/en/build-with-claude/multilingual-support) 顯示 Sonnet 4.5 中文（簡）對英文 MMLU 是 96.9%；最近一篇 [vibe coding 實測論文](https://arxiv.org/abs/2604.14210) 也指出中文 prompt 的問題解決率比英文低 4.5–9.9 個百分點。同樣語意中文 token 數還更多（[Petrov et al. 2023](https://arxiv.org/abs/2305.15425) 量過跨語 token 數可差 15x）。再加上 cc 會跟著「最後一句的語言」調整輸出，中英混打很容易把整段對話拉進中文模式。
2. **Sonnet 偶爾會自己切到韓文 / 日文**。這是已知 bug，繁中使用者在 [#30025](https://github.com/anthropics/claude-code/issues/30025)（中文中突切韓文）跟 [#46846](https://github.com/anthropics/claude-code/issues/46846)（CLAUDE.md 明寫繁中仍回日文）都有重現案例。光靠 prompt / CLAUDE.md 提醒治不住。

這個 proxy 介在 cc 跟 `api.anthropic.com` 中間，依模式翻譯 user prompt、assistant 回覆和後續 history：

- 手動 `/intl` 模式：繁中 prompt 先翻成英文再送過去；模型回的英文原樣回 cc，另一份翻成繁中渲染在本機網頁上。
- 背景反向模式：英文 prompt 先翻成簡中再送過去；模型回的簡中翻回英文再回到 Claude Code TUI。

## 截圖

![繁中與英文雙向同步](screenshots/bilingual-render.png)

上半部是 cc-translate-proxy 的本機繁中 render（瀏覽器 `localhost:9090/<uuid>`），下半部是 cc TUI 看到的英文版對話 — 同一輪對話、不同語言視角。網址 `?nostatusline=1` 是本機隱藏底部 statusline 用的截圖模式 query。

## 運作方式

```
你輸入「幫我重構這個函式」
   │
   ▼
cc-translate-proxy 攔截 /v1/messages
   ├─ 把繁中翻成英文（Gemini Flash / Groq / OpenRouter，自動切換）
   ├─ 英文版送 api.anthropic.com
   └─ 英文回應 fork 一份 → 翻成繁中 → 渲染到本機網頁

CC 看到乾淨英文對話；你瀏覽器讀到繁中 render。
```

## 使用前須知

- **你的 prompt 跟 cc 回覆會送給第三方 LLM**（預設 Gemini Flash）做翻譯。**含敏感內容的 session 不要開**。
- **本機會留兩份對話落檔**：audit log（翻譯前後的完整 prompt / 回覆，JSONL）在 `~/.cc-i18n-proxy/audit/`、render 用的 emit 檔（繁中 markdown）在 `~/.cc-i18n-proxy/emit/`。兩者都是除錯 / 渲染用，內容等同完整對話紀錄，要定期清。
- **個人實驗工具**，不適合 production。預期會碰到 bug。

## 快速開始

需要：Python 3.12+、[`uv`](https://github.com/astral-sh/uv)。

1. Clone 跟安裝：
   ```bash
   git clone https://github.com/0x7067/cc-translate-proxy.git
   cd cc-translate-proxy
   uv sync
   ```

2. 設定翻譯 provider chain（複製範例後編輯）：
   ```bash
   mkdir -p ~/.cc-i18n-proxy
   cp providers.toml.example ~/.cc-i18n-proxy/providers.toml
   ```
   `providers.toml` 內 `default_chain` 控制嘗試順序、前面失敗才 fallback 到下一個。範例預設 `["gemini", "groq", "openrouter"]`，你可以刪到只剩一個或加入 `"ollama"`（本機免 key）。

3. 把對應的 API key 寫進 `~/.cc-i18n-proxy/.env`（變數名要跟 `providers.toml` 裡 `api_key_env` 對齊）：
   ```bash
   cat > ~/.cc-i18n-proxy/.env <<'EOF'
   GEMINI_API_KEY=your-key-here
   # GROQ_API_KEY=...
   # OPENROUTER_API_KEY=...
   EOF
   ```
   申請連結：[Gemini](https://aistudio.google.com/apikey) / [Groq](https://console.groq.com/keys) / [OpenRouter](https://openrouter.ai/keys)。任一個有就能跑，沒設的 provider 會自動從 chain 拿掉。

4. 啟動背景常駐模式：
   ```bash
   ./scripts/proxy-background.sh start
   ```

   這會安裝 / 刷新 macOS user LaunchAgent，只讓 proxy 在背景持續跑。預設使用英文介面、背後送簡中給 Claude，並開啟 `CC_I18N_AUTO_TRANSLATE=1`，所以不需要再打 `/intl`。

5. 之後用 wrapper 開 Claude Code：
   ```bash
   chinese-claude
   ```

   如果還沒把 repo 裡的 wrapper 放進 `$PATH`，在 repo 內用 `./chinese-claude` 也可以。

   它等同於：
   ```bash
   export ANTHROPIC_BASE_URL=http://localhost:8080
   export ENABLE_TOOL_SEARCH=auto
   claude
   ```

背景服務管理：
```bash
./scripts/proxy-background.sh status
./scripts/proxy-background.sh logs
./scripts/proxy-background.sh stop
./scripts/proxy-background.sh restart
./scripts/proxy-background.sh uninstall
```

Render web UI 是選用的，需要瀏覽器畫面時再開：
```bash
./scripts/proxy-background.sh start-render
./scripts/proxy-background.sh stop-render
```

想保留舊的手動 `/intl` 流程，可以改用直通模式手動啟動：
   ```bash
   uv run python -m cc_i18n_proxy > /tmp/proxy.log 2>&1 &
   uv run python scripts/render_server.py > /tmp/render.log 2>&1 &
   ```
然後在任意 `claude` session 內打 `/intl` 啟動翻譯。

預設 proxy 是 **直通模式（passthrough）**，你打什麼它送什麼。`/intl` 把當前 session 加入翻譯白名單：產一個 session UUID、把 marker 塞進對話、之後可以在 `http://localhost:9090/<uuid>` 讀繁中 render。打 `/normal` 退出。

## 設定 `/intl` skill

`/intl` 是 cc 的 skill，不是這個 proxy 的一部分。在 `~/.claude/skills/intl/SKILL.md` 放最小範本：

````markdown
---
name: intl
description: 啟動 cc-translate-proxy 對當前 session 的翻譯模式。
---

產生 12-hex session UUID、把 marker emit 出去，proxy 會在下一個 outbound request 看到 marker 然後把這個 session 加入翻譯白名單。

```bash
UUID=$(python3 -c "import secrets; print(secrets.token_hex(6))")
echo "[CC_I18N_PROXY:ENABLE_THIS_SESSION:uuid=$UUID]"
echo "Render UI: http://localhost:9090/$UUID"
```

讓這個 skill 內容留在對話歷史裡，這樣 `/resume` 跟 proxy 重啟都能自動 recover marker。
````

對應的 `~/.claude/skills/normal/SKILL.md` 要 emit `[CC_I18N_PROXY:DISABLE_THIS_SESSION:uuid=<uuid>]` 退出翻譯。

marker 也可以附上 workspace 資訊（多專案並行時 render 首頁會按 workspace 分組）：

```
[CC_I18N_PROXY:ENABLE_THIS_SESSION:uuid=<uuid>:workspace=<id>:workspace_name=<名稱>]
```

不帶 workspace 時一律歸到 `default` 分組，功能不受影響。

## 注意事項

- **Auto-compaction 可能會把 marker 吃掉**：對話長到 ~50+ 輪時，cc 可能把早期訊息壓縮成 summary，順便把 `/intl` marker 也壓沒了。發生後再打一次 `/intl` 就好。
- **CC 在非 first-party host 會自動關掉 ToolSearch**。設 `ENABLE_TOOL_SEARCH=auto` 把 deferred MCP 載入打開。proxy 不動 `tool_reference` block 所以這樣安全。
- **翻譯不是免費**：Gemini Flash 很便宜但不是零成本。重度使用者要監控花費，failover 機制可以分散到多個 provider。

## 環境變數

| 變數 | 預設 | 用途 |
|---|---|---|
| `CC_I18N_PROXY_HOME` | `~/.cc-i18n-proxy` | 設定 / audit / emit / state 的根目錄 |
| `CC_I18N_PROXY_PORT` | `8080` | proxy 監聽 port |
| `CC_I18N_RENDER_PORT` | `9090` | render server 監聽 port |
| `CC_I18N_PROXY_EMIT_DIR` | `$CC_I18N_PROXY_HOME/emit` | 繁中 emit 檔輸出目錄 |
| `CC_I18N_USER_LANG` | `zh` | 使用者讀寫 / render 的語言 |
| `CC_I18N_CLAUDE_LANG` | `en` | 送進 Claude 的語言 |
| `CC_I18N_REWRITE_TUI` | `auto` | 是否把回傳給 Claude Code TUI 的 assistant 文字也翻回使用者語言；`CC_I18N_CLAUDE_LANG` 不是 `en` 時預設開啟 |
| `CC_I18N_AUTO_TRANSLATE` | `0` | 不需要 `/intl` marker，所有經過 proxy 的 request 都進翻譯模式 |

想反過來用英文介面、背後送簡中給 Claude，可以在啟動 proxy 前設定：

```bash
./scripts/claude-english.sh
```

進入 Claude Code 後直接使用即可；你看到 / 輸入的是英文，Claude-facing 的 user / assistant 對話歷史是簡中。

手動啟動時等同設定：

```bash
export CC_I18N_USER_LANG=en
export CC_I18N_CLAUDE_LANG=zh-Hans
export CC_I18N_AUTO_TRANSLATE=1
```

這樣你在 Claude Code 裡輸入英文，proxy 會先翻成簡中送給 Claude；Claude 的簡中回覆會再翻成英文回給 Claude Code TUI，也會寫進 audit / render。後續 request 內的 assistant 歷史也會從英文翻回簡中，避免 Claude 在上下文裡看到英文 assistant 訊息。

另附 `scripts/render.sh <session-id>`：不開瀏覽器、在 terminal 用 [glow](https://github.com/charmbracelet/glow) 直接 tail 繁中 emit 檔的輕量視圖。

## 測試

```bash
uv run pytest -v
```

## License

MIT — 見 [LICENSE](LICENSE)。
