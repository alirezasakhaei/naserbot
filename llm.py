"""OpenRouter client (OpenAI-compatible chat completions)."""
from __future__ import annotations

import os

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


async def chat(messages: list[dict], model: str | None = None) -> str:
    api_key = os.environ["OPENROUTER_API_KEY"]
    model = model or os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Title": "NaserBot",
    }
    payload = {"model": model, "messages": messages}

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"].strip()


async def summarize_conversation(transcript: str) -> str:
    system = (
        "تو خلاصه‌نویس یک گروه چت تلگرامی هستی برای شخصی که مدتی از گروه دور بوده "
        "و می‌خواهد سریع بفهمد چه گذشته. همیشه به فارسی پاسخ بده، حتی اگر بخشی از "
        "پیام‌ها به زبان دیگری باشد. خلاصه را به صورت بولت‌پوینت بنویس و این موارد "
        "را پوشش بده: چه کسی چه گفت، موضوعات اصلی، تصمیم‌ها، سوال‌های مطرح‌شده، و "
        "هر چیزی که خطاب به شخص غایب گفته شده. کوتاه و دقیق باش."
    )
    user = f"این مکالمه گروهی را خلاصه کن:\n\n{transcript}"
    return await chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
