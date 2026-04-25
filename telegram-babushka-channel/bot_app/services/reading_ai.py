"""Генерация текста расклада через OpenAI API."""

from __future__ import annotations

from openai import APIError, AsyncOpenAI


SYSTEM_PROMPT = """Ты — добрая пожилая гадалка (бабушка), делаешь расклад на картах Таро.
Стиль: тёплый, уважительный, без запугивания и без медицинских/юридических/финансовых советов.
Явно: это символическая интерпретация для размышления, не предсказание судьбы и не истина.
Пиши по-русски. Не используй оскорбительные стереотипы о народах.
"""


async def generate_tarot_reading(
    *,
    api_key: str,
    model: str,
    base_url: str | None,
    question: str,
    tier_usd: int,
) -> tuple[str | None, str]:
    """
    Возвращает (текст_расклада, ошибка_пустая_если_ок).
    """
    if tier_usd <= 5:
        user = (
            f"Вопрос клиента:\n{question}\n\n"
            "Сделай расклад на три карты (Прошлое — Настоящее — Совет/тенденция). "
            "Кратко по 2–4 предложения на каждую позицию, затем общий вывод 2–3 предложения."
        )
    else:
        user = (
            f"Вопрос клиента:\n{question}\n\n"
            "Сделай более развёрнутый расклад: контекст, три–четыре карты с трактовкой, "
            "нюансы и осторожные формулировки, общий совет — без категоричных обещаний."
        )

    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url.rstrip("/")

    client = AsyncOpenAI(**kwargs)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.85,
            max_tokens=1800 if tier_usd > 5 else 900,
        )
    except APIError as e:
        return None, f"OpenAI: {e!s}"
    except Exception as e:
        return None, f"Ошибка генерации: {e!s}"

    choice = resp.choices[0] if resp.choices else None
    text = (choice.message.content or "").strip() if choice and choice.message else ""
    if not text:
        return None, "Пустой ответ модели."
    return text, ""
