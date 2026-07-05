"""Test the in-process translation pipeline (no HTTP)."""
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from cc_i18n_proxy.cache import TranslationCache
from cc_i18n_proxy.pipeline import PipelineResult, TranslationPipeline
from cc_i18n_proxy.translator import TranslationResult


@pytest.mark.asyncio
async def test_pipeline_translates_user_message(tmp_path: Path):
    cache = await TranslationCache.create(tmp_path / "cache.db")
    translator = AsyncMock()
    translator.translate.return_value = TranslationResult(text="Hello", source_lang="zh", target_lang="en")

    pipeline = TranslationPipeline(translator=translator, cache=cache)
    body = {
        "model": "claude-opus-4-7",
        "messages": [{"role": "user", "content": "你好"}],
    }
    result = await pipeline.translate_request_body(body)

    assert isinstance(result, PipelineResult)
    assert result.body["messages"][0]["content"] == "Hello"
    assert result.sources["user"] == "translator_api"
    translator.translate.assert_awaited_once()
    await cache.close()


@pytest.mark.asyncio
async def test_pipeline_uses_cache_on_second_call(tmp_path: Path):
    cache = await TranslationCache.create(tmp_path / "cache.db")
    translator = AsyncMock()
    translator.translate.return_value = TranslationResult(text="Hello", source_lang="zh", target_lang="en")

    pipeline = TranslationPipeline(translator=translator, cache=cache)
    body = {"model": "x", "messages": [{"role": "user", "content": "你好"}]}

    await pipeline.translate_request_body(body)
    translator.translate.reset_mock()

    result = await pipeline.translate_request_body(body)
    assert result.body["messages"][0]["content"] == "Hello"
    assert result.sources["user"] == "cache"
    translator.translate.assert_not_called()
    await cache.close()


@pytest.mark.asyncio
async def test_pipeline_skips_pure_english_user_message(tmp_path: Path):
    cache = await TranslationCache.create(tmp_path / "cache.db")
    translator = AsyncMock()
    pipeline = TranslationPipeline(translator=translator, cache=cache)

    body = {"model": "x", "messages": [{"role": "user", "content": "Hello"}]}
    result = await pipeline.translate_request_body(body)

    assert result.body["messages"][0]["content"] == "Hello"
    assert result.sources["user"] == "fallback_passthrough"  # no CJK → no translation
    translator.translate.assert_not_called()
    await cache.close()


@pytest.mark.asyncio
async def test_pipeline_translates_english_user_message_when_configured(tmp_path: Path):
    cache = await TranslationCache.create(tmp_path / "cache.db")
    translator = AsyncMock()
    translator.translate.return_value = TranslationResult(
        text="请列出这些文件", source_lang="en", target_lang="zh-Hans",
    )

    pipeline = TranslationPipeline(
        translator=translator,
        cache=cache,
        user_lang="en",
        claude_lang="zh-Hans",
    )
    body = {"model": "x", "messages": [{"role": "user", "content": "List these files"}]}
    result = await pipeline.translate_request_body(body)

    assert result.body["messages"][0]["content"] == "请列出这些文件"
    translator.translate.assert_awaited_once_with(
        "List these files", source="en", target="zh-Hans",
    )
    await cache.close()


@pytest.mark.asyncio
async def test_pipeline_cache_is_language_pair_specific(tmp_path: Path):
    cache = await TranslationCache.create(tmp_path / "cache.db")
    translator = AsyncMock()
    translator.translate.return_value = TranslationResult(
        text="简体结果", source_lang="en", target_lang="zh-Hans",
    )

    simplified = TranslationPipeline(
        translator=translator,
        cache=cache,
        user_lang="en",
        claude_lang="zh-Hans",
    )
    await simplified.translate_request_body(
        {"model": "x", "messages": [{"role": "user", "content": "Hello"}]},
    )

    translator.translate.reset_mock()
    translator.translate.return_value = TranslationResult(
        text="繁體結果", source_lang="en", target_lang="zh-Hant",
    )
    traditional = TranslationPipeline(
        translator=translator,
        cache=cache,
        user_lang="en",
        claude_lang="zh-Hant",
    )
    result = await traditional.translate_request_body(
        {"model": "x", "messages": [{"role": "user", "content": "Hello"}]},
    )

    assert result.body["messages"][0]["content"] == "繁體結果"
    translator.translate.assert_awaited_once_with("Hello", source="en", target="zh-Hant")
    await cache.close()


@pytest.mark.asyncio
async def test_pipeline_grace_degrade_on_translator_error(tmp_path: Path):
    cache = await TranslationCache.create(tmp_path / "cache.db")
    translator = AsyncMock()
    translator.translate.side_effect = RuntimeError("Gemini timeout")

    pipeline = TranslationPipeline(translator=translator, cache=cache)
    body = {"model": "x", "messages": [{"role": "user", "content": "你好"}]}
    result = await pipeline.translate_request_body(body)

    assert result.body["messages"][0]["content"] == "你好"  # passthrough
    assert result.sources["user"] == "fallback_passthrough"
    await cache.close()


@pytest.mark.asyncio
async def test_pipeline_does_not_modify_assistant_messages(tmp_path: Path):
    cache = await TranslationCache.create(tmp_path / "cache.db")
    translator = AsyncMock()
    translator.translate.return_value = TranslationResult(text="Hi", source_lang="zh", target_lang="en")
    pipeline = TranslationPipeline(translator=translator, cache=cache)

    body = {
        "messages": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "Hi! 中文 stays as is."},
            {"role": "user", "content": "再見"},
        ]
    }
    result = await pipeline.translate_request_body(body)

    assert result.body["messages"][1]["content"] == "Hi! 中文 stays as is."  # untouched
    assert result.body["messages"][0]["content"] == "Hi"
    assert result.body["messages"][2]["content"] == "Hi"
    await cache.close()
