"""Dual-provider LLM client (OpenAI + Gemini). Offline-safe if keys are absent."""
from __future__ import annotations
import os
from typing import Literal, Optional
from openai import OpenAI
import google.generativeai as genai
Provider = Literal["openai","gemini"]

def verify_llm_provider_available(provider: Optional[str]=None)->None:
    p = (provider or "").strip().lower() if provider else None
    if p in (None,""):
        return
    if p=="openai" and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Missing OPENAI_API_KEY.")
    if p=="gemini" and not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("Missing GEMINI_API_KEY.")
    if p not in ("openai","gemini"):
        raise ValueError(f"Unsupported provider: {provider}")

class LLMClient:
    def __init__(self, provider: Provider):
        self.provider = provider
        if provider=="openai":
            api_key=os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY not found.")
            self._openai = OpenAI(api_key=api_key)
            self._openai_model = os.getenv("OPENAI_MODEL","gpt-4o-mini")
        elif provider=="gemini":
            api_key=os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY not found.")
            genai.configure(api_key=api_key)
            self._gemini_model=os.getenv("GEMINI_MODEL","gemini-2.5-pro")
            self._gemini_fallbacks=[self._gemini_model,"gemini-2.5-flash","gemini-2.0-flash"]
        else:
            raise ValueError("Unsupported provider.")

    def complete(self, prompt: str, max_tokens: int=900)->str:
        if self.provider=="openai":
            resp = self._openai.chat.completions.create(
                model=self._openai_model,
                messages=[{"role":"system","content":"You are a factual, conservative compliance and sensor analyst."},
                          {"role":"user","content":prompt}],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        last_err: Optional[Exception]=None
        for m in self._gemini_fallbacks:
            try:
                model = genai.GenerativeModel(model_name=m, generation_config={"temperature":0.2,"max_output_tokens":max_tokens})
                r = model.generate_content(prompt)
                return (r.text or "").strip()
            except Exception as e:
                last_err=e
        raise last_err if last_err else RuntimeError("Gemini completion failed.")
