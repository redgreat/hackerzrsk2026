"""全局配置：唯一入口，全部来自环境变量 / backend/.env（嵌套字段用 `__` 分隔）。"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-in-prod"

Purpose = Literal["customer", "evaluator", "coach", "hint"]


class ModelPrice(BaseModel):
    """模型单价：元 / 百万 token。"""

    input: float = 0.0
    output: float = 0.0


class PurposeModel(BaseModel):
    """按用途覆盖模型与温度；model 为空时使用 LLMSettings.model。"""

    model: str | None = None
    temperature: float = 0.3
    max_tokens: int | None = None


class LLMSettings(BaseModel):
    provider: Literal["stub", "openai"] = "stub"
    base_url: str | None = None
    api_key: str | None = None
    model: str = "deepseek-chat"
    timeout_seconds: float = 60
    max_retries: int = 2
    # 部分厂商（如百炼）需要额外参数，例如 {"enable_thinking": false}
    extra_body: dict | None = None
    customer: PurposeModel = PurposeModel(temperature=0.8, max_tokens=300)
    evaluator: PurposeModel = PurposeModel(temperature=0.1, max_tokens=600)
    coach: PurposeModel = PurposeModel(temperature=0.2, max_tokens=3000)
    hint: PurposeModel = PurposeModel(temperature=0.4, max_tokens=300)
    pricing: dict[str, ModelPrice] = Field(
        default_factory=lambda: {"deepseek-chat": ModelPrice(input=2.0, output=8.0)}
    )

    def for_purpose(self, purpose: Purpose) -> PurposeModel:
        return getattr(self, purpose)


class EmbeddingSettings(BaseModel):
    enabled: bool = False
    base_url: str | None = None
    api_key: str | None = None
    model: str = "text-embedding-v3"
    # 需与迁移中 knowledge_chunks.embedding 的维度一致
    dimensions: int = 1024


class SpeechSettings(BaseModel):
    asr_provider: Literal["none", "openai", "stub"] = "none"
    tts_provider: Literal["none", "openai", "stub"] = "none"
    base_url: str | None = None
    api_key: str | None = None
    asr_model: str = "whisper-1"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"
    asr_price_per_minute: float = 0.0
    tts_price_per_10k_chars: float = 0.0


class WeComSettings(BaseModel):
    corp_id: str | None = None
    agent_id: str | None = None
    secret: str | None = None
    api_base: str = "https://qyapi.weixin.qq.com"

    @property
    def enabled(self) -> bool:
        return bool(self.corp_id and self.agent_id and self.secret)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://coach:coach@127.0.0.1:5432/ai_coach"
    db_pool_size: int = 10

    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_hours: int = 24 * 7
    dev_login_enabled: bool = True
    # 可查看全员统计的工号；为空时任何登录用户都可查看（仅聚合数据）
    admin_userids: list[str] = Field(default_factory=list)

    scenarios_dir: Path = PROJECT_DIR / "scenarios"
    knowledge_dir: Path = PROJECT_DIR / "knowledge"
    frontend_dist: Path = PROJECT_DIR / "frontend" / "dist"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    mask_pii: bool = True
    # 人工带教单次成本（元），用于成本对比统计
    manual_coaching_cost_yuan: float = 25.0

    llm: LLMSettings = LLMSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    speech: SpeechSettings = SpeechSettings()
    wecom: WeComSettings = WeComSettings()

    @property
    def psycopg_conninfo(self) -> str:
        """LangGraph checkpointer 使用的原生 psycopg 连接串。"""
        return self.database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    def validate_for_runtime(self) -> None:
        if self.app_env == "prod":
            if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
                raise RuntimeError("生产环境必须设置不少于 32 位的 JWT_SECRET")
            if self.llm.provider == "stub":
                raise RuntimeError("生产环境不能使用 stub 模型")


@lru_cache
def get_settings() -> Settings:
    return Settings()
