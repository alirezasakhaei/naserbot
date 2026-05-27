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


async def summarize_conversation(transcript: str, requester_name: str = "") -> str:
    names = "، ".join(GANG_MEMBERS)
    system = (
        "تو ناصری، یه ربات باحال و شوخ‌طبع تو گروه تلگرامی یه دار و دسته از رفقا. "
        "وقتی یکی /summary می‌زنه، باید خلاصه‌ی چیزی که از دست داده رو بهش بگی. "
        "همیشه فقط فارسی جواب بده. لحن خودمونی و یه ذره شوخ، ولی بدون اغراق و بدون "
        "تیکه‌ی اضافه. "
        "\n\nقالب جواب:"
        "\n- فقط یه پاراگراف کوتاه (نه بولت، نه تیتر، نه چند بخش)."
        "\n- اصلاً مارک‌داون استفاده نکن. نه ستاره برای بولد، نه بک‌تیک، نه #، نه -. "
        "متن خام فارسی. اموجی اوکیه اگه کم و به‌جا باشه."
        "\n\nقانون مهم درباره‌ی اسم‌ها:"
        "\n- توی هر خط ترنسکریپت قبل از «:» اسم فرستنده اومده. *دقیقاً* همون اسم رو "
        "استفاده کن. حق نداری اسم رو حدس بزنی یا تغییر بدی."
        "\n- اگه اسم با حروف انگلیسی بود (مثل «Alireza Sakhaei»)، فقط در صورتی که "
        "مطمئنی، معادلش از این لیست رو بنویس، وگرنه همون انگلیسی رو بذار: "
        f"{names}."
        "\n- هیچ‌کس از این لیست رو بدون اینکه واقعاً تو ترنسکریپت حرفی زده باشه، نیار."
    )
    addressed_to = f"\n\n(درخواست‌دهنده: {requester_name})" if requester_name else ""
    user = f"این گفتگوی گروه رو در یک پاراگراف کوتاه و خام (بدون مارک‌داون) خلاصه کن:{addressed_to}\n\n{transcript}"
    return await chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
