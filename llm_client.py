from __future__ import annotations

import os
from typing import Literal, Optional

from openai import OpenAI
import google.generativeai as genai

Provider = Literal["openai", "gemini"]


def verify_llm_provider_available(provider: Optional[str] = None) -> None:
    p = (provider or "").strip().lower() if provider else None

    if p in (None, ""):
        missing = []
        if not os.getenv("OPENAI_API_KEY"):
            missing.append("OPENAI_API_KEY")
        if not os.getenv("GEMINI_API_KEY"):
            missing.append("GEMINI_API_KEY")
        if missing:
            raise RuntimeError(
                "Missing required environment variables for dual-LLM run: "
                + ", ".join(missing)
            )
        return

    if p == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("Missing OPENAI_API_KEY.")
        return

    if p == "gemini":
        if not os.getenv("GEMINI_API_KEY"):
            raise RuntimeError("Missing GEMINI_API_KEY.")
        return

    raise ValueError(f"Unsupported provider: {provider}")


class LLMClient:
    def __init__(self, provider: Provider):
        self.provider: Provider = provider

        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not found in environment.")
            self._openai = OpenAI(api_key=api_key)
            self._openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        elif provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY not found in environment.")
            genai.configure(api_key=api_key)

            self._gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
            self._gemini_fallbacks = [
                self._gemini_model,
                "gemini-2.5-flash",
                "gemini-2.0-flash",
            ]
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def complete(self, prompt: str, max_tokens: int = 800) -> str:
        if self.provider == "openai":
            return self._complete_openai(prompt, max_tokens)
        if self.provider == "gemini":
            return self._complete_gemini(prompt, max_tokens)
        raise RuntimeError("Invalid provider state")

    def _complete_openai(self, prompt: str, max_tokens: int) -> str:
        resp = self._openai.chat.completions.create(
            model=self._openai_model,
            messages=[
                {"role": "system", "content": "You are a factual, conservative compliance analyst."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _complete_gemini(self, prompt: str, max_tokens: int) -> str:
        last_err = None
        for model_name in self._gemini_fallbacks:
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config={
                        "temperature": 0.2,
                        "max_output_tokens": max_tokens,
                    },
                )
                resp = model.generate_content(prompt)
                return (resp.text or "").strip()
            except Exception as e:
                last_err = e
                continue
        raise last_err if last_err else RuntimeError("Gemini completion failed.")
