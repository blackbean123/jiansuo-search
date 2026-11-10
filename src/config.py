import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

TENCENT_SECRET_ID = os.getenv("TENCENTCLOUD_SECRET_ID", "")
TENCENT_SECRET_KEY = os.getenv("TENCENTCLOUD_SECRET_KEY", "")


@dataclass
class LLMProvider:
    name: str
    api_key: str
    base_url: str
    model: str


PROVIDERS: dict[str, LLMProvider] = {
    "deepseek": LLMProvider(
        name="deepseek",
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    ),
    "glm": LLMProvider(
        name="glm",
        api_key=os.getenv("GLM_API_KEY", ""),
        base_url=os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        model=os.getenv("GLM_MODEL", "glm-4-flash"),
    ),
    "hunyuan": LLMProvider(
        name="hunyuan",
        api_key=os.getenv("HUNYUAN_API_KEY", ""),
        base_url=os.getenv("HUNYUAN_BASE_URL", "https://api.hunyuan.cloud.tencent.com/v1"),
        model=os.getenv("HUNYUAN_MODEL", "hunyuan-pro"),
    ),
    "custom": LLMProvider(
        name="custom",
        api_key=os.getenv("CUSTOM_API_KEY", ""),
        base_url=os.getenv("CUSTOM_BASE_URL", ""),
        model=os.getenv("CUSTOM_MODEL", ""),
    ),
}

DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")