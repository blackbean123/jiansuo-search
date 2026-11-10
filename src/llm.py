import json
import re

from openai import OpenAI

from src.config import PROVIDERS, LLMProvider


class LLM:
    def __init__(
        self,
        provider_name: str = "",
        *,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
    ):
        if api_key and base_url and model:
            self.cfg = LLMProvider(name="custom", api_key=api_key, base_url=base_url, model=model)
        else:
            if provider_name not in PROVIDERS:
                raise ValueError(f"未知的 LLM provider: {provider_name}，可选: {list(PROVIDERS.keys())}")
            cfg = PROVIDERS[provider_name]
            if not cfg.api_key:
                raise ValueError(f"未配置 {provider_name} 的 API key，请在 .env 中设置")
            self.cfg = cfg
        self.client = OpenAI(api_key=self.cfg.api_key, base_url=self.cfg.base_url)

    def chat(self, system: str, user: str, temperature: float = 0.7) -> str:
        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return resp.choices[0].message.content

    def chat_json(self, system: str, user: str) -> dict:
        raw = self.chat(system, user, temperature=0.3)
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        if "```" in text:
            match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()
        return json.loads(text)