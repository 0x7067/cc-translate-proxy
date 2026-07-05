from cc_i18n_proxy.config import Config


def test_rewrite_tui_defaults_off_for_existing_english_upstream(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_I18N_PROXY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CC_I18N_PROXY_EMIT_DIR", str(tmp_path / "emit"))

    cfg = Config.from_env()

    assert cfg.user_lang == "zh"
    assert cfg.claude_lang == "en"
    assert cfg.rewrite_tui_response is False
    assert cfg.auto_translate is False


def test_rewrite_tui_defaults_on_for_simplified_chinese_upstream(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_I18N_PROXY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CC_I18N_PROXY_EMIT_DIR", str(tmp_path / "emit"))
    monkeypatch.setenv("CC_I18N_USER_LANG", "en")
    monkeypatch.setenv("CC_I18N_CLAUDE_LANG", "zh-Hans")

    cfg = Config.from_env()

    assert cfg.user_lang == "en"
    assert cfg.claude_lang == "zh-Hans"
    assert cfg.rewrite_tui_response is True


def test_rewrite_tui_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_I18N_PROXY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CC_I18N_PROXY_EMIT_DIR", str(tmp_path / "emit"))
    monkeypatch.setenv("CC_I18N_CLAUDE_LANG", "zh-Hans")
    monkeypatch.setenv("CC_I18N_REWRITE_TUI", "0")

    cfg = Config.from_env()

    assert cfg.rewrite_tui_response is False


def test_auto_translate_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_I18N_PROXY_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CC_I18N_PROXY_EMIT_DIR", str(tmp_path / "emit"))
    monkeypatch.setenv("CC_I18N_AUTO_TRANSLATE", "1")

    cfg = Config.from_env()

    assert cfg.auto_translate is True
