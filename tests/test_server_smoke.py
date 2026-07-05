"""Smoke test: server starts and forwards request through full pipeline."""
import json
from unittest.mock import AsyncMock

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from cc_i18n_proxy.audit import AuditLogWriter
from cc_i18n_proxy.cache import TranslationCache
from cc_i18n_proxy.config import Config
from cc_i18n_proxy.emitter import FileEmitter
from cc_i18n_proxy.pipeline import TranslationPipeline
from cc_i18n_proxy.server import _post_response_fork, build_app
from cc_i18n_proxy.translator import NamedAdapter, TranslationResult, TranslatorChain

_FAKE_UUID = "deadbeef0000"
_ENABLE = f"[CC_I18N_PROXY:ENABLE_THIS_SESSION:uuid={_FAKE_UUID}]"


@pytest.fixture
async def app_client(tmp_path, tmp_config):
    cache = await TranslationCache.create(tmp_path / "cache.db")
    translator = AsyncMock()
    translator.translate.side_effect = lambda text, source, target: TranslationResult(
        text="Hello" if source == "zh" else "你好",
        source_lang=source,
        target_lang=target,
    )
    named = NamedAdapter(name="mock", adapter=translator)
    chain = TranslatorChain(
        default_chain=[named],
        enabled_by_name={"mock": named},
        active_head_reader=lambda: None,
    )
    pipeline = TranslationPipeline(translator=chain, cache=cache)
    audit = AuditLogWriter(tmp_path / "audit")
    emitter = FileEmitter(tmp_path / "emit")
    app = build_app(tmp_config, pipeline=pipeline, chain=chain, audit=audit, emitter=emitter)
    yield TestClient(app), translator
    await cache.close()


@pytest.fixture
async def english_visible_app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_I18N_PROXY_HOME", str(tmp_path / "proxy_home"))
    monkeypatch.setenv("CC_I18N_PROXY_EMIT_DIR", str(tmp_path / "emit"))
    monkeypatch.setenv("CC_I18N_USER_LANG", "en")
    monkeypatch.setenv("CC_I18N_CLAUDE_LANG", "zh-Hans")
    monkeypatch.setenv("CC_I18N_AUTO_TRANSLATE", "1")
    cfg = Config.from_env()
    cache = await TranslationCache.create(tmp_path / "cache.db")
    translator = AsyncMock()

    def translate(text, source, target):
        if source == "en" and target == "zh-Hans":
            if text == "Here are the files":
                return TranslationResult(text="这里是文件", source_lang=source, target_lang=target)
            return TranslationResult(text="请列出文件", source_lang=source, target_lang=target)
        if source == "zh-Hans" and target == "en":
            return TranslationResult(text="Here are the files", source_lang=source, target_lang=target)
        return TranslationResult(text=f"{source}->{target}:{text}", source_lang=source, target_lang=target)

    translator.translate.side_effect = translate
    named = NamedAdapter(name="mock", adapter=translator)
    chain = TranslatorChain(
        default_chain=[named],
        enabled_by_name={"mock": named},
        active_head_reader=lambda: None,
    )
    pipeline = TranslationPipeline(
        translator=chain,
        cache=cache,
        user_lang=cfg.user_lang,
        claude_lang=cfg.claude_lang,
        translate_assistant_history=cfg.rewrite_tui_response,
    )
    audit = AuditLogWriter(tmp_path / "audit")
    emitter = FileEmitter(tmp_path / "emit")
    app = build_app(cfg, pipeline=pipeline, chain=chain, audit=audit, emitter=emitter)
    yield TestClient(app), translator, chain, audit, emitter, cfg
    await cache.close()


@respx.mock
def test_server_translates_user_and_forwards(app_client):
    client, translator = app_client
    forward = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi there"}],
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })
    )
    body = {
        "model": "claude-opus-4-7",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": f"{_ENABLE}你好"}],
    }
    resp = client.post("/v1/messages", json=body, headers={"x-api-key": "test"})

    assert resp.status_code == 200
    sent = json.loads(forward.calls[0].request.content)
    assert sent["messages"][0]["content"] == "Hello"


@respx.mock
def test_server_translates_english_user_to_simplified_chinese(english_visible_app_client):
    client, translator, *_ = english_visible_app_client
    forward = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "这里是文件"}],
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })
    )
    body = {
        "model": "claude-opus-4-7",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": f"{_ENABLE}List files"}],
    }
    resp = client.post("/v1/messages", json=body, headers={"x-api-key": "test"})

    assert resp.status_code == 200
    assert resp.json()["content"][0]["text"] == "Here are the files"
    sent = json.loads(forward.calls[0].request.content)
    assert sent["messages"][0]["content"] == "请列出文件"
    assert any(
        call.kwargs == {"source": "en", "target": "zh-Hans"}
        for call in translator.translate.await_args_list
    )


@respx.mock
def test_server_auto_translates_without_intl_marker(english_visible_app_client):
    client, *_ = english_visible_app_client
    forward = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "这里是文件"}],
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })
    )
    body = {
        "model": "claude-opus-4-7",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "List files"}],
    }
    resp = client.post("/v1/messages", json=body, headers={"x-api-key": "test"})

    assert resp.status_code == 200
    assert resp.json()["content"][0]["text"] == "Here are the files"
    sent = json.loads(forward.calls[0].request.content)
    assert sent["messages"][0]["content"] == "请列出文件"


@respx.mock
def test_server_translates_assistant_history_to_simplified_chinese(english_visible_app_client):
    client, *_ = english_visible_app_client
    forward = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "这里是文件"}],
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })
    )
    body = {
        "model": "claude-opus-4-7",
        "max_tokens": 100,
        "messages": [
            {"role": "user", "content": f"{_ENABLE}List files"},
            {"role": "assistant", "content": "Here are the files"},
            {"role": "user", "content": "List files"},
        ],
    }
    resp = client.post("/v1/messages", json=body, headers={"x-api-key": "test"})

    assert resp.status_code == 200
    sent = json.loads(forward.calls[0].request.content)
    assert sent["messages"][0]["content"] == "请列出文件"
    assert sent["messages"][1]["content"] == "这里是文件"
    assert sent["messages"][2]["content"] == "请列出文件"


@respx.mock
def test_server_rewrites_sse_response_to_english_for_tui(english_visible_app_client):
    client, *_ = english_visible_app_client
    sse = (
        'event: message_start\n'
        'data: {"type":"message_start","message":{"usage":{"input_tokens":1}}}\n\n'
        'event: content_block_delta\n'
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"这里"}}\n\n'
        'event: content_block_delta\n'
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"是文件"}}\n\n'
        'event: message_delta\n'
        'data: {"type":"message_delta","usage":{"output_tokens":2}}\n\n'
    ).encode()
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, content=sse, headers={"content-type": "text/event-stream"})
    )
    body = {
        "model": "claude-opus-4-7",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": f"{_ENABLE}List files"}],
    }
    resp = client.post("/v1/messages", json=body, headers={"x-api-key": "test"})

    assert resp.status_code == 200
    assert "Here are the files" in resp.text
    assert "这里" not in resp.text
    assert "是文件" not in resp.text
    assert '"output_tokens":2' in resp.text


@pytest.mark.asyncio
async def test_post_response_fork_translates_simplified_chinese_assistant_to_english(
    english_visible_app_client,
):
    _, translator, chain, audit, emitter, cfg = english_visible_app_client

    await _post_response_fork(
        cfg,
        {"chain": chain, "audit": audit, "emitter": emitter},
        "sess123",
        {"messages": [{"role": "user", "content": "List files"}]},
        {"messages": [{"role": "user", "content": "请列出文件"}]},
        json.dumps({
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": "这里是文件"}],
            "usage": {"input_tokens": 1, "output_tokens": 2},
        }).encode(),
        {"user": "translator_api"},
        {"user": "ok"},
        user_provider="mock",
        user_failover_attempts=[],
        user_failover_errors=[],
    )

    entry = json.loads((audit._dir / "sess123.jsonl").read_text().strip())
    assert entry["assistant_en"] == "这里是文件"
    assert entry["assistant_zh"] == "Here are the files"
    assert entry["user_lang"] == "en"
    assert entry["claude_lang"] == "zh-Hans"
    assert any(
        call.kwargs == {"source": "zh-Hans", "target": "en"}
        for call in translator.translate.await_args_list
    )


@respx.mock
def test_cache_hit_no_translator_call_on_repeat(app_client):
    client, translator = app_client
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant",
            "content": [{"type": "text", "text": "Hi"}], "model": "x",
            "usage": {"input_tokens": 5, "output_tokens": 2},
        })
    )
    body = {"model": "x", "max_tokens": 1, "messages": [{"role": "user", "content": f"{_ENABLE}你好"}]}

    client.post("/v1/messages", json=body, headers={"x-api-key": "test"})
    client.post("/v1/messages", json=body, headers={"x-api-key": "test"})

    user_translate_calls = sum(
        1 for call in translator.translate.await_args_list
        if call.kwargs.get("source") == "zh"
    )
    assert user_translate_calls == 1, "second call should hit cache, not translate user msg again"


@respx.mock
def test_resume_with_50_turn_history_zero_user_translation(app_client):
    """Simulate /resume: same history sent twice. All user msgs cache-hit."""
    client, translator = app_client
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, json={
            "id": "m", "type": "message", "role": "assistant",
            "content": [{"type": "text", "text": "ok"}], "model": "x",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })
    )
    history = [
        {"role": "user", "content": f"{_ENABLE}問題 0" if i == 0 else f"問題 {i}"}
        for i in range(50)
    ]
    body = {"model": "x", "max_tokens": 1, "messages": history}

    client.post("/v1/messages", json=body, headers={"x-api-key": "test"})
    first_user_calls = sum(1 for c in translator.translate.await_args_list if c.kwargs.get("source") == "zh")
    assert first_user_calls == 50

    translator.translate.reset_mock()
    client.post("/v1/messages", json=body, headers={"x-api-key": "test"})
    second_user_calls = sum(1 for c in translator.translate.await_args_list if c.kwargs.get("source") == "zh")
    assert second_user_calls == 0, "/resume should yield 100% cache hit on user messages"
