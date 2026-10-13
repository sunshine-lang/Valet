from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        extra="ignore",
    )

    # 界面名称、接口标题、默认系统提示词都用这个名字。换项目时改这里即可。
    agent_name: str = "Valet"
    dashscope_api_key: str = ""
    dashscope_model: str = "deepseek-v4-flash-0731"
    deepseek_api_key: str = ""
    moonshot_api_key: str = ""
    zai_api_key: str = ""
    minimax_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    xai_api_key: str = ""
    groq_api_key: str = ""
    mistral_api_key: str = ""
    openrouter_api_key: str = ""
    cerebras_api_key: str = ""
    together_api_key: str = ""
    fireworks_api_key: str = ""
    bocha_api_key: str = ""
    tavily_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    database_url: str = f"sqlite+aiosqlite:///{REPO_ROOT / '.valet' / 'valet.db'}"
    web_origin: str = "http://localhost:5173"
    display_timezone: str = "Asia/Shanghai"
    # 文件工具的项目根。空字符串表示当前仓库；测试可改成临时目录。
    workspace_root: str = ""
    # 旧配置名。workspace_root 为空时仍可作为项目根。
    upload_dir: str = ""
    # 空字符串表示用仓库下的 skills；用户自己安装的技能在 data/skills
    skills_dir: str = ""
    user_skills_dir: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
