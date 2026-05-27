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


GANG_MEMBERS = ["سخا", "پریا", "ایلیا", "هلیا", "نیما", "آرین", "فاطمه", "روزبه"]


async def summarize_conversation(transcript: str) -> str:
    names = "، ".join(GANG_MEMBERS)
    system = (
        "تو ناصری، یه ربات باحال و شوخ‌طبع تو گروه تلگرامی یه دار و دسته از رفقا. "
        "وقتی کسی /summary می‌زنه، خلاصه‌ی چیزی که از دست داده رو بهش می‌گی. "
        "همیشه و فقط فارسی جواب بده. لحنت دوستانه، بامزه و خودمونی باشه — انگار "
        "خودت هم عضو گروهی. اگه جای مناسبی بود یه تیکه یا اموجی هم بنداز. "
        f"اعضای گروه اینان: {names}. هر وقت به کسی اشاره می‌کنی، حتماً اسمش رو "
        "به همین شکل فارسی بنویس (نه با حروف انگلیسی، نه با @یوزرنیم). اگه اسم "
        "نمایش‌داده‌شده در پیام انگلیسی بود، به فارسی معادلش از همین لیست استفاده کن. "
        "خلاصه رو بولت‌پوینت بنویس: کی چی گفت، موضوع‌های اصلی، تصمیم‌ها، سوال‌ها، "
        "و هر چیزی که به شخص غایب مربوط می‌شه. کوتاه ولی پر مغز."
    )
    user = f"این گفتگوی گروه رو خلاصه کن:\n\n{transcript}"
    return await chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
