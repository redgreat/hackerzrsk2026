"""进程级依赖容器：在 lifespan 中创建，挂到 app.state.container。"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.services.knowledge import KnowledgeBase
from app.services.llm import LLMGateway
from app.services.practice import PracticeService
from app.services.scenarios import ScenarioRegistry
from app.services.speech import SpeechService
from app.services.wecom import WeComClient
from app.services.wecom_chat import WeComChatBot


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    scenarios: ScenarioRegistry
    llm: LLMGateway
    knowledge: KnowledgeBase
    speech: SpeechService
    wecom: WeComClient
    practice: PracticeService
    wecom_bot: WeComChatBot
