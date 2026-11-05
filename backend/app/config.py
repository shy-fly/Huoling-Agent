"""Application configuration."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]  # workspace root
BACKEND_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DEFAULT = ROOT / "knowledge"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{BACKEND_ROOT / 'data' / 'digester.db'}"
    llm_provider: str = "deepseek"
    llm_api_base: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-flash"
    llm_timeout_ms: int = 60000
    llm_max_tokens_polish: int = 2048
    llm_max_tokens_qa: int = 4096
    # DeepSeek V4 默认思考模式；关闭以把 token 预算留给正文
    llm_thinking_enabled: bool = False
    app_env: str = "development"
    app_release: str = "firefairy-contest-4.0.0"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    knowledge_root: str = str(KNOWLEDGE_DEFAULT)
    rag_top_k: int = 5
    rag_use_vector: bool = True
    use_llm: bool = False
    admin_token: str = ""

    @property
    def knowledge_path(self) -> Path:
        p = Path(self.knowledge_root)
        if not p.is_absolute():
            p = ROOT / p
        return p

    @property
    def uploads_path(self) -> Path:
        """用户上传文献缓存目录（须在可写 data 卷，Docker 下 knowledge 为只读挂载）。"""
        return BACKEND_ROOT / "data" / "uploads"


settings = Settings()
