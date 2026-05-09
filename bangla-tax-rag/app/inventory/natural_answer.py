from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_OLLAMA_URL = "http://localhost:11434"
_OLLAMA_MODEL = "qwen3:8b"
_OLLAMA_TIMEOUT = 12.0  # seconds — fast enough to not block the user

_SYSTEM_PROMPT = """\
You are a warm, helpful assistant for Sonjoy Boutique — a Bangladeshi fashion boutique.
You answer customer questions in the SAME language the customer used.
- If the customer wrote in Bangla → respond fully in Bangla.
- If in Banglish (romanized Bangla) → respond in Banglish.
- If in English → respond in English.
- Mixed input → match the dominant language.

Rules you MUST follow:
1. Use ONLY the product information provided below. Never mention products not listed.
2. If a product is out of stock, say so clearly — do not suggest it as available.
3. Be warm and conversational, like a boutique staff member — not robotic.
4. Keep responses concise — 2-4 sentences for simple queries, up to 6 for complex ones.
5. When recommending products, mention the price and stock count.
6. Do not repeat the customer's question back to them.
7. End with a natural follow-up question when appropriate (e.g., "কোন সাইজ দরকার?" or "Would you like to place an order?").
"""

_PRODUCT_CONTEXT_TEMPLATE = """\
Available products for this query:
{products}

Customer question: {question}
"""

_BANGLA_EXAMPLES = [
    {
        "question": "লাল জামদানি শাড়ি আছে?",
        "products": "1. Lotus Buti Dhakai Jamdani Saree - Red | Price: BDT 6,800 | Stock: 4",
        "answer": "জি আছে! Lotus Buti Dhakai Jamdani শাড়িটা লাল রঙে পাওয়া যাচ্ছে — মাত্র BDT 6,800। এখন ৪টা stock আছে। নিতে চাইলে বলুন, সাইজ ও পেমেন্ট মেথড কনফার্ম করে দিতে পারব।",
    },
    {
        "question": "delivery charge koto?",
        "products": "",
        "answer": "Dhaka-r moddhe delivery charge BDT 80 — tobe BDT 5,000-er upore order korle free! Dhaka-r baaire BDT 150. Same day express delivery-o available BDT 150-e (diner 12-tar age order dile).",
    },
]


def build_natural_answer_prompt(
    question: str,
    product_snippets: list[dict[str, Any]],
    language_hint: str = "auto",
) -> list[dict[str, str]]:
    """
    Build the messages list for a chat completion call.
    product_snippets: list of {name, price, stock, fabric, color, ...}
    Returns: [{"role": "system", "content": ...}, {"role": "user", "content": ...}]
    """
    if product_snippets:
        lines = []
        for i, p in enumerate(product_snippets[:5], 1):
            price_str = f"BDT {p.get('price', 0):,.0f}" if p.get("price") else "Price N/A"
            stock_str = str(p.get("stock", 0))
            attrs = p.get("attributes", {})
            attr_parts = []
            for k in ("color", "fabric", "size", "occasion", "work_type"):
                v = attrs.get(k)
                if v:
                    attr_parts.append(f"{k}: {v}")
            attr_str = " | ".join(attr_parts)
            lines.append(f"{i}. {p.get('name', 'Product')} | {price_str} | Stock: {stock_str}" + (f" | {attr_str}" if attr_str else ""))
        products_text = "\n".join(lines)
    else:
        products_text = "(No specific products — this is a policy or general question)"

    user_content = _PRODUCT_CONTEXT_TEMPLATE.format(
        products=products_text,
        question=question,
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
    ]
    # Add few-shot examples if relevant
    lang = language_hint.casefold()
    if "bangla" in lang or any(ord(c) > 0x0980 for c in question):
        ex = _BANGLA_EXAMPLES[0]
        messages += [
            {"role": "user", "content": _PRODUCT_CONTEXT_TEMPLATE.format(products=ex["products"], question=ex["question"])},
            {"role": "assistant", "content": ex["answer"]},
        ]
    elif "banglish" in lang:
        ex = _BANGLA_EXAMPLES[1]
        messages += [
            {"role": "user", "content": _PRODUCT_CONTEXT_TEMPLATE.format(products=ex["products"], question=ex["question"])},
            {"role": "assistant", "content": ex["answer"]},
        ]
    messages.append({"role": "user", "content": user_content})
    return messages


def generate_ollama_answer(
    question: str,
    product_snippets: list[dict[str, Any]],
    language_hint: str = "auto",
    ollama_url: str = _OLLAMA_URL,
    model: str = _OLLAMA_MODEL,
    timeout: float = _OLLAMA_TIMEOUT,
    fallback: str = "",
) -> str | None:
    """
    Call Ollama chat to generate a warm, grounded natural-language answer.
    Returns the cleaned answer string, or None on any failure (caller uses template).
    Never raises — all errors are caught and logged at DEBUG level.
    """
    messages = build_natural_answer_prompt(question, product_snippets, language_hint)
    try:
        resp = httpx.post(
            f"{ollama_url}/api/chat",
            json={"model": model, "messages": messages, "stream": False,
                  "options": {"temperature": 0.25, "num_predict": 400}},
            timeout=timeout,
        )
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "").strip()
        if not raw:
            return None
        result = parse_natural_answer(raw, fallback=fallback)
        return result if len(result) > 20 else None
    except Exception as exc:
        logger.debug("Ollama natural answer failed (using template): %s", exc)
        return None


def parse_natural_answer(raw: str, fallback: str) -> str:
    """Clean up LLM output. Strip any preamble, enforce max length."""
    text = raw.strip()
    # Remove common preambles the LLM might add
    for prefix in ("Sure!", "Of course!", "Certainly!", "Here is", "Here's", "Response:", "Answer:"):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip(" ,:")
    # Enforce max 600 chars to avoid wall-of-text responses
    if len(text) > 600:
        # Cut at last sentence boundary
        cut = text[:600].rfind("।")
        if cut < 400:
            cut = text[:600].rfind(".")
        if cut > 100:
            text = text[:cut + 1]
        else:
            text = text[:600] + "…"
    return text if len(text) > 20 else fallback
