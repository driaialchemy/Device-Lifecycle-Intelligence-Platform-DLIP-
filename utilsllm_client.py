# utils/llm_client.py
# Unified deterministic LLM client for OpenAI + Anthropic
# Enforces strict factuality and safe defaults.

import os
import time
import random
from typing import Optional, Dict

# OpenAI
from openai import OpenAI

# Anthropic
import anthropic


class LLMClient:
    """
    Centralized interface for LLM access.
    Determines provider, enforces deterministic generation,
    and applies strict factuality constraints.
    """

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()

        # API keys
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")

        if self.provider == "openai" and not self.openai_key:
            raise ValueError("OPENAI_API_KEY is missing but provider=openai")

        if self.provider == "anthropic" and not self.anthropic_key:
            raise ValueError("ANTHROPIC_API_KEY is missing but provider=anthropic")

        # Initialize clients
        self.openai_client = OpenAI(api_key=self.openai_key) if self.openai_key else None
        self.anthropic_client = anthropic.Anthropic(api_key=self.anthropic_key) if self.anthropic_key else None

        # Deterministic seed for reproducibility
        self.seed = 42
        random.seed(self.seed)

        # Model selection
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4.1")
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-3-7-sonnet-2025")

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------
    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        """
        Unified completion endpoint.
        Agents call this method only.
        """

        safe_prompt = self._apply_safety(prompt)

        if self.provider == "openai":
            return self._openai_complete(safe_prompt, max_tokens)

        elif self.provider == "anthropic":
            return self._anthropic_complete(safe_prompt, max_tokens)

        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    # ------------------------------------------------------------------
    # PROVIDER: OPENAI
    # ------------------------------------------------------------------
    def _openai_complete(self, prompt: str, max_tokens: int) -> str:
        retries = 3
        for attempt in range(retries):
            try:
                response = self.openai_client.chat.completions.create(
                    model=self.openai_model,
                    messages=[
                        {"role": "system", "content": self._system_preamble()},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=max_tokens,
                    temperature=0.0,      # deterministic
                    top_p=1.0,
                    seed=self.seed
                )

                return response.choices[0].message["content"]

            except Exception as e:
                if attempt == retries - 1:
                    raise RuntimeError(f"OpenAI completion failed: {e}")
                time.sleep(1.0)

    # ------------------------------------------------------------------
    # PROVIDER: ANTHROPIC
    # ------------------------------------------------------------------
    def _anthropic_complete(self, prompt: str, max_tokens: int) -> str:
        retries = 3
        for attempt in range(retries):
            try:
                response = self.anthropic_client.messages.create(
                    model=self.anthropic_model,
                    max_tokens=max_tokens,
                    temperature=0.0,
                    top_p=1.0,
                    messages=[
                        {"role": "system", "content": self._system_preamble()},
                        {"role": "user", "content": prompt}
                    ]
                )
                return response.content[0].text

            except Exception as e:
                if attempt == retries - 1:
                    raise RuntimeError(f"Anthropic completion failed: {e}")
                time.sleep(1.0)

    # ------------------------------------------------------------------
    # SAFETY + FACTUALITY LAYER
    # ------------------------------------------------------------------
    def _system_preamble(self) -> str:
        """
        Strict factuality + evidence-only rule for agents.
        This prevents hallucinated standards or made-up details.
        """
        return (
            "You are an evidence-bound audit agent. "
            "You must cite only the data, tool outputs, and standards explicitly provided. "
            "You must not invent standards, rules, metrics, or numbers. "
            "If evidence is insufficient, state uncertainty explicitly. "
            "High-confidence claims require explicit references to evidence. "
            "Do not fabricate citations or sources."
        )

    def _apply_safety(self, prompt: str) -> str:
        """
        Applies deterministic seed + factuality prefix.
        """
        return (
            f"[DETERMINISTIC_MODE_SEED={self.seed}]\n"
            f"[STRICT_FACTUALITY=ON]\n"
            + prompt
        )


# ------------------------------------------------------------------
# VALIDATION UTIL
# ------------------------------------------------------------------
def verify_llm_provider_available():
    """
    Ensures that the chosen provider has a valid API key.
    Called at Orchestrator startup.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()

    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for provider 'openai'.")

    if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is required for provider 'anthropic'.")
