"""
Copilot provider chain: Gemini first, Grok (xAI) as fallback.

WHY A CHAIN
-----------
The copilot is the one part of this app that depends on somebody else's
server. A free-tier quota reset, a 429, a regional outage or a model rename
all look identical from here: the panel goes blank at the worst possible
moment. So we try providers in order and only report failure when every one
of them has failed, with the reason each gave.

Both providers get the SAME system prompt and the SAME grounding context, so
an answer does not change character when the chain falls through. The reply
says which provider served it — hiding that would make the demo less honest,
not more impressive.

CONFIGURE
---------
    GEMINI_API_KEY   primary      (Google AI Studio)
    XAI_API_KEY      fallback     (console.x.ai)

Optional:
    GEMINI_MODEL     default gemini-2.5-flash  (free tier)
    XAI_MODEL        default grok-4.7
    COPILOT_ORDER    default "gemini,grok"     — reorder or drop providers

Either key alone is enough. With neither, /copilot returns 503 and says so.
"""

from __future__ import annotations

import json
import os
import threading
import time

import httpx

TIMEOUT = 30.0

SYSTEM_PROMPT = (
    "You are the Q-VIRA copilot, explaining a hybrid quantum-classical "
    "bioinformatics dashboard to a technical judge.\n"
    "RULES:\n"
    "1. Use ONLY the numbers in CONTEXT. Never invent or estimate a figure.\n"
    "2. If the answer is not in CONTEXT, say you do not have it.\n"
    "3. Be precise about what is real: a 4-qubit PennyLane simulation with "
    "a data re-uploading ansatz, physicochemical descriptors (not ESM-2 "
    "unless CONTEXT says so), and a deterministic SEIR scenario.\n"
    "4. Never claim quantum advantage. At 4 qubits there is none; the "
    "circuit is a feasibility study.\n"
    "5. This is a research prototype, not a clinical or public-health tool.\n"
    "6. Answer in under 120 words."
)


def _user_message(question: str, context: dict | None) -> str:
    return (f"CONTEXT:\n{json.dumps(context or {}, indent=2)}\n\n"
            f"QUESTION: {question}")


class ProviderError(RuntimeError):
    """One provider failed. The chain keeps going."""


# --------------------------------------------------------------- gemini

def _gemini(question: str, context: dict | None) -> tuple[str, str]:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ProviderError("GEMINI_API_KEY not set")

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user",
                      "parts": [{"text": _user_message(question, context)}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400},
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(url, headers={"x-goog-api-key": key}, json=payload)
    except Exception as exc:
        raise ProviderError(f"{type(exc).__name__} reaching Gemini")

    if resp.status_code != 200:
        raise ProviderError(f"HTTP {resp.status_code} {_terse(resp.text)}")
    try:
        parts = resp.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, ValueError):
        raise ProviderError("unreadable response shape")
    if not text:
        raise ProviderError("empty response")
    return text, model


# ----------------------------------------------------------------- grok

_XAI_BASE = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
_discovered_model: str | None = None
_discover_lock = threading.Lock()


def _xai_discover_model(key: str) -> str | None:
    """Ask xAI what it actually serves.

    Model names move (grok-3-mini -> grok-4 -> grok-4.7 ...). A hard-coded
    name that 404s a month from now is exactly the failure this fallback
    exists to prevent, so on a model error we look the list up once and
    cache it for the process.
    """
    global _discovered_model
    with _discover_lock:
        if _discovered_model:
            return _discovered_model
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.get(f"{_XAI_BASE}/models",
                               headers={"Authorization": f"Bearer {key}"})
            if r.status_code != 200:
                return None
            ids = [m.get("id", "") for m in r.json().get("data", [])]
        except Exception:
            return None
        # text chat models only - skip the image/video generators
        chat = [i for i in ids if "grok" in i.lower()
                and not any(x in i.lower() for x in ("imagine", "image", "video"))]
        if not chat:
            return None
        _discovered_model = sorted(chat)[-1]      # newest-looking id
        return _discovered_model


def _xai_call(key: str, model: str, question: str, context: dict | None):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_message(question, context)},
        ],
        "temperature": 0.2,
        "max_tokens": 400,
    }
    with httpx.Client(timeout=TIMEOUT) as client:
        return client.post(f"{_XAI_BASE}/chat/completions",
                           headers={"Authorization": f"Bearer {key}",
                                    "Content-Type": "application/json"},
                           json=payload)


def _grok(question: str, context: dict | None) -> tuple[str, str]:
    key = os.getenv("XAI_API_KEY")
    if not key:
        raise ProviderError("XAI_API_KEY not set")

    model = os.getenv("XAI_MODEL", "grok-4.7")
    try:
        resp = _xai_call(key, model, question, context)
        # a renamed or retired model -> look up what this key can actually use
        if resp.status_code in (400, 404):
            found = _xai_discover_model(key)
            if found and found != model:
                model = found
                resp = _xai_call(key, model, question, context)
    except Exception as exc:
        raise ProviderError(f"{type(exc).__name__} reaching xAI")

    if resp.status_code != 200:
        raise ProviderError(f"HTTP {resp.status_code} {_terse(resp.text)}")
    try:
        text = resp.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError, AttributeError):
        raise ProviderError("unreadable response shape")
    if not text:
        raise ProviderError("empty response")
    return text, model


# ----------------------------------------------------------------- chain

PROVIDERS = {"gemini": _gemini, "grok": _grok}
LABEL = {"gemini": "Gemini", "grok": "Grok"}


def _terse(body: str, n: int = 140) -> str:
    """Upstream error bodies are long and often contain the request echoed
    back. Keep enough to diagnose, not enough to leak the prompt."""
    return " ".join((body or "").split())[:n]


def order() -> list[str]:
    raw = os.getenv("COPILOT_ORDER", "gemini,grok")
    chain = [p.strip().lower() for p in raw.split(",") if p.strip().lower() in PROVIDERS]
    return chain or ["gemini", "grok"]


def configured() -> list[str]:
    """Providers that have a key, in chain order."""
    env = {"gemini": "GEMINI_API_KEY", "grok": "XAI_API_KEY"}
    return [p for p in order() if os.getenv(env[p])]


def ask(question: str, context: dict | None) -> dict:
    """Walk the chain. First provider to answer wins.

    Raises RuntimeError only when every configured provider has failed; the
    message names each failure so the UI can show why, rather than a bare
    'something went wrong'.
    """
    attempts, started = [], time.time()
    for name in order():
        try:
            text, model = PROVIDERS[name](question, context)
        except ProviderError as exc:
            attempts.append({"provider": name, "ok": False, "detail": str(exc)})
            continue
        return {
            "answer": text,
            "provider": LABEL[name],
            "model": model,
            "fell_back": len(attempts) > 0,
            "attempts": attempts,
            "elapsed_s": round(time.time() - started, 2),
        }

    if all(a["detail"].endswith("not set") for a in attempts):
        raise RuntimeError(
            "Copilot disabled: no provider key is set. Add GEMINI_API_KEY "
            "and/or XAI_API_KEY to the environment."
        )
    detail = "; ".join(f"{LABEL[a['provider']]}: {a['detail']}" for a in attempts)
    raise RuntimeError(f"All copilot providers failed. {detail}")
