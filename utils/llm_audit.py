# -*- coding: utf-8 -*-

import json
import os
import re
from typing import Any, Dict, Iterable, Optional

import config

MISSING_API_KEY_MESSAGE = "未配置 API KEY: DASHSCOPE_API_KEY"

SYSTEM_PROMPT = (
    "You are an enterprise audit assistant. "
    "Output pure JSON only. Do not output markdown or extra text. "
    'Return exactly: {"risk_level":"HIGH|MEDIUM|LOW","reason":"short Chinese audit comment"}.'
)


def _get_conf(name: str, default: Optional[str] = None) -> Optional[str]:
    env_val = os.getenv(name)
    if env_val:
        return env_val
    return getattr(config, name, default)


def _build_invoice_context(items: Optional[Iterable[str]], ocr_json: Optional[Dict[str, Any]]) -> str:
    lines = [str(x).strip() for x in (items or []) if str(x).strip()]
    ocr_excerpt = ""
    if isinstance(ocr_json, dict):
        try:
            ocr_excerpt = json.dumps(ocr_json, ensure_ascii=False)[:2000]
        except Exception:
            ocr_excerpt = str(ocr_json)[:2000]

    return (
        "Assess invoice audit risk based on the following content.\n"
        f"Items: {lines or ['(none)']}\n"
        f"OCR summary: {ocr_excerpt or '(none)'}\n"
        "Return strict JSON."
    )


def _build_text_context(
    ocr_text: str,
    claim_category: str = "office_expense",
    extra_context: Optional[Dict[str, Any]] = None,
) -> str:
    extra = ""
    if isinstance(extra_context, dict) and extra_context:
        extra = json.dumps(extra_context, ensure_ascii=False)
    return (
        f"Claim category: {claim_category}\n"
        f"Extra context: {extra or '{}'}\n"
        "OCR text:\n"
        f"{ocr_text}\n"
        "Return strict JSON."
    )


def _messages_from_context(context_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context_text},
    ]


def _response_to_dict(resp: Any) -> Dict[str, Any]:
    if isinstance(resp, dict):
        return resp
    to_dict = getattr(resp, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass
    output = getattr(resp, "output", None)
    if output is not None:
        return {"output": output}
    return {"raw": str(resp)}


def _extract_content(resp: Any) -> str:
    data = _response_to_dict(resp)
    output = data.get("output")

    if isinstance(output, dict):
        text = output.get("text")
        if isinstance(text, str) and text.strip():
            return text

        choices = output.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message") if isinstance(first, dict) else None
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    chunks = []
                    for part in content:
                        if isinstance(part, dict):
                            text_part = part.get("text")
                            if isinstance(text_part, str) and text_part.strip():
                                chunks.append(text_part.strip())
                    if chunks:
                        return "\n".join(chunks)
            text = first.get("text") if isinstance(first, dict) else None
            if isinstance(text, str):
                return text

    if isinstance(output, str):
        return output
    return str(data.get("raw", ""))


def _clean_json_text(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = cleaned.replace("```json", "")
    cleaned = cleaned.replace("```JSON", "")
    cleaned = cleaned.replace("```", "")
    cleaned = cleaned.strip()
    return cleaned


def _normalize_level(level: Any) -> str:
    val = str(level or "").strip().upper()
    if val in {"HIGH", "MEDIUM", "LOW"}:
        return val
    return "MEDIUM"


def _parse_audit_json(text: str) -> Dict[str, str]:
    cleaned = _clean_json_text(text)
    if not cleaned:
        return {"risk_level": "MEDIUM", "reason": "Model returned empty content"}

    try:
        parsed = json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            return {"risk_level": "MEDIUM", "reason": cleaned[:120] or "JSON parse failed"}
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return {"risk_level": "MEDIUM", "reason": cleaned[:120] or "JSON parse failed"}

    if not isinstance(parsed, dict):
        return {"risk_level": "MEDIUM", "reason": "Model output schema is invalid"}

    level = _normalize_level(parsed.get("risk_level"))
    reason = str(parsed.get("reason") or "No audit reason provided").strip()
    if not reason:
        reason = "No audit reason provided"

    return {"risk_level": level, "reason": reason}


def _call_generation(context_text: str) -> Any:
    api_key = _get_conf("DASHSCOPE_API_KEY")
    model_name = _get_conf("LLM_MODEL_NAME", "qwen-turbo")
    if not api_key or str(api_key).strip() in {"", "sk-..."}:
        raise RuntimeError(MISSING_API_KEY_MESSAGE)

    import dashscope
    from dashscope import Generation

    dashscope.api_key = api_key
    messages = _messages_from_context(context_text)

    try:
        return Generation.call(
            model=model_name,
            messages=messages,
            temperature=0.1,
            result_format="message",
        )
    except TypeError:
        prompt = f"{SYSTEM_PROMPT}\n\n{context_text}"
        return Generation.call(
            model=model_name,
            prompt=prompt,
            temperature=0.1,
        )


def semantic_audit(
    items: Optional[Iterable[str]] = None,
    ocr_json: Optional[Dict[str, Any]] = None,
    **_: Any,
) -> Dict[str, str]:
    try:
        ctx = _build_invoice_context(items=items, ocr_json=ocr_json)
        resp = _call_generation(ctx)
        text = _extract_content(resp)
        return _parse_audit_json(text)
    except Exception as exc:
        err_text = str(exc)
        if MISSING_API_KEY_MESSAGE in err_text:
            return {"risk_level": "MEDIUM", "reason": MISSING_API_KEY_MESSAGE}
        return {"risk_level": "MEDIUM", "reason": f"AI audit failed: {exc}"}


def semantic_audit_items(
    items: Optional[Iterable[str]] = None,
    ocr_json: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, str]:
    return semantic_audit(items=items, ocr_json=ocr_json, **kwargs)


def audit_semantic(*args: Any, **kwargs: Any) -> Dict[str, str]:
    return semantic_audit(*args, **kwargs)


def analyze_invoice_semantic(*args: Any, **kwargs: Any) -> Dict[str, str]:
    return semantic_audit(*args, **kwargs)


def llm_semantic_audit(*args: Any, **kwargs: Any) -> Dict[str, str]:
    return semantic_audit(*args, **kwargs)


def semantic_audit_report(
    ocr_text: str,
    claim_category: str = "office_expense",
    extra_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        ctx = _build_text_context(
            ocr_text=ocr_text,
            claim_category=claim_category,
            extra_context=extra_context,
        )
        resp = _call_generation(ctx)
        raw_text = _extract_content(resp)
        parsed = _parse_audit_json(raw_text)
        report = f"risk_level: {parsed['risk_level']}\nreason: {parsed['reason']}"
        return {
            "ok": True,
            "model": _get_conf("LLM_MODEL_NAME", "qwen-turbo"),
            "report": report,
            "raw": _response_to_dict(resp),
            "risk_level": parsed["risk_level"],
            "reason": parsed["reason"],
        }
    except Exception as exc:
        err_text = str(exc)
        if MISSING_API_KEY_MESSAGE in err_text:
            err_text = MISSING_API_KEY_MESSAGE
        return {
            "ok": False,
            "model": _get_conf("LLM_MODEL_NAME", "qwen-turbo"),
            "report": "",
            "raw": {"error": err_text},
            "risk_level": "MEDIUM",
            "reason": err_text if err_text == MISSING_API_KEY_MESSAGE else f"AI audit failed: {exc}",
        }
