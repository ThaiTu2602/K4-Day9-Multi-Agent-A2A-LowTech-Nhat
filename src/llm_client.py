"""Thin adapter around the Groq cloud API (OpenAI-compatible endpoint).

Model name is declared here in source (not only in .env) per the lab's
grading requirement: every agent must use a <=10B parameter model and the
model name must be visible in code, not hidden behind an environment
variable. llama-3.1-8b-instant is an 8B-parameter instruction-tuned model
served by Groq, fast enough for 50 cases x 5 handoffs within the
competition window.

Only GROQ_API_KEY is read from .env (secrets belong in .env, never in
source, per README section 9.4); the model name itself stays hardcoded.
"""

from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

load_dotenv()

MODEL_NAME = "llama-3.1-8b-instant"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")


class LLMUnavailableError(RuntimeError):
    pass


def chat(system_prompt: str, user_prompt: str, temperature: float = 0.1, timeout: float = 60.0) -> str:
    """Single-turn chat completion against the Groq API. Raises
    LLMUnavailableError if the key is missing or the call fails, so callers
    can decide how to degrade (this pipeline never lets LLM output affect
    computed numbers/decisions, only human-readable trace narration)."""
    if not GROQ_API_KEY:
        raise LLMUnavailableError("GROQ_API_KEY not set in .env")
    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except requests.RequestException as exc:
        raise LLMUnavailableError(f"Groq API call failed: {exc}") from exc
