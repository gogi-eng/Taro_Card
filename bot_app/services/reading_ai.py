"""Генерация текста расклада через OpenAI API."""

from __future__ import annotations

from openai import APIError, AsyncOpenAI


SYSTEM_PROMPT = """Ты — добрая пожилая гадалка (бабушка), делаешь расклад на картах Таро.
Стиль: тёплый, уважительный, без запугивания и без медицинских/юридических/финансовых советов.
Явно: это символическая интерпретация для размышления, не предсказание судьбы и не истина.
Пиши по-русски. Не используй оскорбительные стереотипы о народах.
"""

MAJOR_ARCANA_RU = [
    "Шут",
    "Маг",
    "Верховная жрица",
    "Императрица",
    "Император",
    "Иерофант",
    "Влюблённые",
    "Колесница",
    "Справедливость",
    "Отшельник",
    "Колесо Фортуны",
    "Сила",
    "Повешенный",
    "Смерть",
    "Умеренность",
    "Дьявол",
    "Башня",
    "Звезда",
    "Луна",
    "Солнце",
    "Суд",
    "Мир",
]


def esc_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _offline_free_card(question: str) -> tuple[str, str]:
    """
    Короткий расклад без API: одна Старшая аркана, стабильно от хэша вопроса.
    Возвращает (текст для чата, короткое имя для картинки).
    """
    h = abs(hash((question or "").strip().lower()))
    name = MAJOR_ARCANA_RU[h % len(MAJOR_ARCANA_RU)]
    text = (
        "✨ <b>Ответ бота (бесплатно, одна карта)</b>\n\n"
        f"🃏 <b>Карта дня:</b> «{name}»\n\n"
        "<b>Что это значит (коротко):</b>\n"
        "Символически просит не ловить «сроки», а смотреть на опору, порядок в семье и зрелость решений. "
        "Семейные события складываются в своей последовательности; спешка и паника обычно только путают. "
        "Это образ для размышления, а не дата в календаре и не клинический прогноз.\n\n"
        f"<b>Ваш вопрос:</b> «{esc_html(question[:500])}»\n\n"
        "<i>Мини-режим без интернета. Более развёрнуто и с другими картами — кнопка «Заказать расклад».</i>"
    )
    return text, name


def _split_card_line_from_ai(text: str) -> tuple[str, str | None]:
    """
    Ожидаем первую строку вида «КАРТА: Название» — убираем её из ответа и шлём название на картинку.
    """
    lines = (text or "").strip().split("\n")
    if not lines:
        return text, None
    first = lines[0].strip()
    key = "карта:"
    if first.lower().startswith(key):
        card = first[len(key) :].strip()
        if card.startswith("«") and card.endswith("»"):
            card = card[1:-1]
        body = "\n".join(lines[1:]).strip()
        return body, (card or None)
    return text.strip(), None


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


async def generate_free_one_card_reading(
    *,
    api_key: str | None,
    model: str,
    base_url: str | None,
    question: str,
) -> tuple[str, str, str | None]:
    """
    (текст_в_чат_HTML, err, название_для_картинки).
    err пуст, если в чат можно отправить text.
    """
    q = (question or "").strip()
    if not q:
        return "", "Пустой вопрос.", None
    if not api_key:
        body, cname = _offline_free_card(q)
        return body, "", cname
    user = (
        f"Вопрос клиента:\n{q}\n\n"
        "Сделай бесплатный мини-расклад: одна Старшая аркана. "
        "СТРОГО первая строка: «КАРТА: [точное русское имя]». Со второй строки — 3–6 предложений: "
        "смысл карты по отношению к вопросу, мягкий совет, без пугающих формулировок. "
        "Только буквы, без HTML."
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
            max_tokens=600,
        )
    except APIError as e:
        body, cname = _offline_free_card(q)
        return body, f"OpenAI: {e!s}", cname
    except Exception as e:
        body, cname = _offline_free_card(q)
        return body, f"Ошибка: {e!s}", cname

    choice = resp.choices[0] if resp.choices else None
    raw = (choice.message.content or "").strip() if choice and choice.message else ""
    if not raw:
        body, cname = _offline_free_card(q)
        return body, "Пустой ответ нейросети.", cname
    body_raw, cname = _split_card_line_from_ai(raw)
    body_html = (
        "✨ <b>Ответ (бесплатно, 1 карта)</b>\n\n"
        + (f"🃏 <b>Карта дня:</b> «{esc_html(cname)}»\n\n" if cname else "")
        + f"<b>Толкование:</b>\n{esc_html(body_raw or raw)}"
    )
    return body_html, "", cname
