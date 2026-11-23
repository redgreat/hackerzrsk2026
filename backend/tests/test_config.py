from app.core.config import Settings


def test_settings_read_yaml_from_config_path(tmp_path, monkeypatch):
    f = tmp_path / "config.yml"
    f.write_text(
        "app_env: prod\n"
        "database_url: postgresql+psycopg://u:p@db.example.com:5432/zrcoach\n"
        "llm:\n  provider: openai\n  model: qwen-plus\n"
        "wecom:\n  corp_id: wwabc\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_PATH", str(f))
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings()
    assert s.app_env == "prod"
    assert s.database_url.endswith("/zrcoach")
    assert s.llm.provider == "openai" and s.llm.model == "qwen-plus"
    assert s.wecom.corp_id == "wwabc"


def test_env_overrides_single_field(tmp_path, monkeypatch):
    f = tmp_path / "config.yml"
    f.write_text("app_env: prod\n", encoding="utf-8")
    monkeypatch.setenv("CONFIG_PATH", str(f))
    monkeypatch.setenv("APP_ENV", "test")
    assert Settings().app_env == "test"


def test_missing_config_file_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "missing.yml"))
    monkeypatch.delenv("APP_ENV", raising=False)
    assert Settings().app_env == "dev"
