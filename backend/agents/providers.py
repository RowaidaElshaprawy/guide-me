# backend/agents/providers.py
from abc import ABC, abstractmethod
from backend.core.config import settings
import re
import time


class ProviderError(Exception):
    pass


class BaseProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, temperature: float = 0.1) -> str:
        pass

    @abstractmethod
    def is_healthy(self) -> bool:
        pass


class GeminiProvider(BaseProvider):
    def __init__(self):
        try:
            from google import genai
            from google.genai import types
            self._client = genai.Client(api_key=settings.gemini_api_key)
            self._types = types
            model = settings.gemini_model
            self._model = model.replace("models/", "") if model.startswith("models/") else model
            self._available = True
            print("[GeminiProvider] Initialized.")
        except Exception as e:
            print(f"[GeminiProvider] Init failed: {e}")
            self._available = False

    def is_healthy(self) -> bool:
        return self._available and bool(settings.gemini_api_key)

    def generate(self, prompt: str, temperature: float = 0.1) -> str:
        if not self.is_healthy():
            raise ProviderError("GeminiProvider unavailable.")
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=1500,
                ),
            )
            return response.text.strip()
        except Exception as e:
            error_str = str(e).lower()
            if "403" in error_str or "permission_denied" in error_str:
                raise ProviderError(f"PERMISSION_DENIED: {e}")
            if "429" in error_str or "quota" in error_str or "rate" in error_str:
                raise ProviderError(f"RATE_LIMITED: {e}")
            raise ProviderError(f"GEMINI_ERROR: {e}")


class GroqProvider(BaseProvider):
    def __init__(self):
        try:
            if not settings.groq_api_key:
                self._available = False
                print("[GroqProvider] No key configured.")
                return
            from groq import Groq
            self._client = Groq(api_key=settings.groq_api_key)
            self._model = settings.groq_model
            self._available = True
            print("[GroqProvider] Initialized.")
        except Exception as e:
            print(f"[GroqProvider] Init failed: {e}")
            self._available = False

    def is_healthy(self) -> bool:
        return self._available and bool(settings.groq_api_key)

    def generate(self, prompt: str, temperature: float = 0.1) -> str:
        if not self.is_healthy():
            raise ProviderError("GroqProvider unavailable.")
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=1500,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise ProviderError(f"GROQ_ERROR: {e}")


class ProviderRouter:
    def __init__(self):
        self._gemini = GeminiProvider()
        self._groq = GroqProvider()
        self.last_provider = "none"

    def generate(self, prompt: str, temperature: float = 0.1) -> str:
        if self._gemini.is_healthy():
            try:
                result = self._gemini.generate(prompt, temperature)
                self.last_provider = "gemini"
                return result
            except ProviderError as e:
                print(f"[ProviderRouter] Gemini failed: {e} — switching to Groq")
                time.sleep(1)

        if self._groq.is_healthy():
            try:
                result = self._groq.generate(prompt, temperature)
                self.last_provider = "groq"
                print("[ProviderRouter] Groq fallback succeeded.")
                return result
            except ProviderError as e:
                raise ProviderError(f"All providers exhausted: {e}")

        raise ProviderError("No providers healthy. Check API keys in .env")

    @staticmethod
    def clean_json(raw: str) -> str:
        return re.sub(r"```json|```", "", raw).strip()