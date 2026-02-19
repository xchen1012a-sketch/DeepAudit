from __future__ import annotations

import json
import os
import re
from typing import Any

import config

DEFAULT_ERROR_MESSAGE = "AI 服务暂时繁忙，请稍后重试或转人工审核。"
DEFAULT_SUGGESTION = "建议结合规则引擎结果进行人工复核，并保留审计留痕。"
FALLBACK_NOTE = "AI 响应格式异常，已切换规则兜底分析。"

SYSTEM_PROMPT = (
    "You are an enterprise reimbursement auditor. "
    "Return JSON only, no markdown and no extra text. "
    'Schema: {"risk_level":"High|Medium|Low","risk_score":0-100,'
    '"summary":"...","details":"...","suggestion":"..."}'
)

HIGH_RISK_KEYWORDS = (
    "ktv",
    "酒吧",
    "会所",
    "夜总会",
    "spa",
    "按摩",
    "娱乐",
    "礼品卡",
    "私人消费",
)

MEDIUM_RISK_KEYWORDS = (
    "招待",
    "餐饮",
    "住宿",
    "加油",
    "打车",
    "交通",
    "烟酒",
)


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _clamp_score(value: Any, fallback: int = 55) -> int:
    try:
        score = int(float(str(value).strip()))
    except Exception:
        score = fallback
    return max(0, min(100, score))


def _normalize_level(level: Any) -> str:
    text = _safe_text(level).upper()
    if text in {"HIGH", "H"}:
        return "High"
    if text in {"LOW", "L"}:
        return "Low"
    return "Medium"


def _score_by_level(level: str) -> int:
    if level == "High":
        return 85
    if level == "Low":
        return 25
    return 55


def _to_dict_if_possible(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    try:
        return dict(value)
    except Exception:
        return None


def _strip_json_block(text: str) -> str:
    cleaned = _safe_text(text)
    return cleaned.replace("```json", "").replace("```JSON", "").replace("```", "").strip()


def _extract_json_dict(text: str) -> dict[str, Any] | None:
    cleaned = _strip_json_block(text)
    if not cleaned:
        return None

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    for block in re.findall(r"\{[\s\S]*?\}", cleaned):
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue

    level_match = re.search(r"risk_level\s*[:=]\s*\"?(High|Medium|Low|HIGH|MEDIUM|LOW)\"?", cleaned)
    if not level_match:
        return None
    score_match = re.search(r"risk_score\s*[:=]\s*(\d{1,3})", cleaned)
    summary_match = re.search(r"summary\s*[:=]\s*\"([^\"]{1,200})\"", cleaned)
    details_match = re.search(r"details\s*[:=]\s*\"([^\"]{1,400})\"", cleaned)
    suggestion_match = re.search(r"suggestion\s*[:=]\s*\"([^\"]{1,300})\"", cleaned)
    return {
        "risk_level": level_match.group(1),
        "risk_score": int(score_match.group(1)) if score_match else None,
        "summary": summary_match.group(1) if summary_match else "",
        "details": details_match.group(1) if details_match else "",
        "suggestion": suggestion_match.group(1) if suggestion_match else "",
    }


def _response_to_dict(resp: Any) -> dict[str, Any]:
    as_dict = _to_dict_if_possible(resp)
    if as_dict is not None:
        return as_dict

    to_dict = None
    try:
        to_dict = getattr(resp, "to_dict")
    except Exception:
        to_dict = None

    if callable(to_dict):
        try:
            value = to_dict()
            if isinstance(value, dict):
                return value
            dict_value = _to_dict_if_possible(value)
            if dict_value is not None:
                return dict_value
            return {"raw": value}
        except Exception:
            pass

    try:
        output = getattr(resp, "output")
        return {"output": output}
    except Exception:
        return {"raw": _safe_text(resp)}


def _extract_content_text(resp: Any) -> str:
    data = _response_to_dict(resp)
    output = data.get("output")

    output_dict = _to_dict_if_possible(output) if output is not None else None
    if output_dict:
        text = output_dict.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

        choices = output_dict.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else _to_dict_if_possible(choices[0]) or {}
            message = first.get("message") if isinstance(first, dict) else None
            msg_dict = message if isinstance(message, dict) else _to_dict_if_possible(message) or {}

            content = msg_dict.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    item_dict = item if isinstance(item, dict) else _to_dict_if_possible(item) or {}
                    part = _safe_text(item_dict.get("text"))
                    if part:
                        parts.append(part)
                if parts:
                    return "\n".join(parts)

            first_text = first.get("text") if isinstance(first, dict) else None
            if isinstance(first_text, str) and first_text.strip():
                return first_text.strip()

    if isinstance(output, str) and output.strip():
        return output.strip()
    return _safe_text(data.get("raw"))


class QwenAuditor:
    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        self.api_key = _safe_text(api_key) or _safe_text(os.getenv("DASHSCOPE_API_KEY")) or _safe_text(
            getattr(config, "DASHSCOPE_API_KEY", "")
        )
        self.model_name = _safe_text(model_name) or _safe_text(getattr(config, "LLM_MODEL_NAME", "qwen-turbo"))

    def _build_context(
        self,
        ocr_text: str,
        claim_category: str,
        extra_context: dict[str, Any] | None = None,
    ) -> str:
        extra = json.dumps(extra_context or {}, ensure_ascii=False)
        return (
            f"Claim category: {claim_category}\n"
            f"Extra context: {extra}\n"
            "Invoice text:\n"
            f"{_safe_text(ocr_text)[:12000]}"
        )

    def _call_qwen(self, context: str) -> Any:
        if not self.api_key:
            raise RuntimeError("missing_dashscope_api_key")

        import dashscope
        from dashscope import Generation

        dashscope.api_key = self.api_key
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ]
        try:
            return Generation.call(
                model=self.model_name,
                messages=messages,
                temperature=0.1,
                result_format="message",
            )
        except TypeError:
            prompt = f"{SYSTEM_PROMPT}\n\n{context}"
            return Generation.call(
                model=self.model_name,
                prompt=prompt,
                temperature=0.1,
            )

    def _normalize_success(self, payload: dict[str, Any]) -> dict[str, Any]:
        level = _normalize_level(payload.get("risk_level"))
        score = _clamp_score(payload.get("risk_score"), fallback=_score_by_level(level))
        summary = _safe_text(payload.get("summary") or payload.get("reason"), "未发现明显高风险信号。")
        details = _safe_text(payload.get("details") or payload.get("reason"), "模型未返回详细理由。")
        suggestion = _safe_text(payload.get("suggestion"), DEFAULT_SUGGESTION)
        return {
            "status": "success",
            "data": {
                "risk_level": level,
                "risk_score": score,
                "summary": summary,
                "details": details,
                "suggestion": suggestion,
            },
        }

    def _fallback_success(self, ocr_text: str, reason: str = FALLBACK_NOTE) -> dict[str, Any]:
        source = _safe_text(ocr_text).lower()
        level = "Low"
        summary = "未发现明显高风险信号。"
        details = reason
        suggestion = DEFAULT_SUGGESTION

        if any(token in source for token in HIGH_RISK_KEYWORDS):
            level = "High"
            summary = "疑似命中高风险消费场景，请重点复核。"
            details = f"{reason} 文本中出现娱乐/非经营性消费关键词。"
            suggestion = "建议转人工复核并补充业务凭证，必要时直接驳回。"
        elif any(token in source for token in MEDIUM_RISK_KEYWORDS):
            level = "Medium"
            summary = "存在中风险费用特征，建议补充说明。"
            details = f"{reason} 文本中出现招待或差旅类关键词。"
            suggestion = "建议补充事由、参与人和审批链路后再判定。"

        return {
            "status": "success",
            "data": {
                "risk_level": level,
                "risk_score": _score_by_level(level),
                "summary": summary,
                "details": details,
                "suggestion": suggestion,
            },
        }

    def _error_result(self, message: str = DEFAULT_ERROR_MESSAGE) -> dict[str, str]:
        return {"status": "error", "message": _safe_text(message, DEFAULT_ERROR_MESSAGE)}

    def audit(
        self,
        ocr_text: str,
        claim_category: str = "office_expense",
        extra_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = _safe_text(ocr_text)
        if not text:
            return self._error_result("未识别到可审计文本，请先检查票据影像。")

        try:
            context = self._build_context(
                ocr_text=text,
                claim_category=claim_category,
                extra_context=extra_context,
            )
            raw_resp = self._call_qwen(context)
            content = _extract_content_text(raw_resp)
            parsed = _extract_json_dict(content)
            if isinstance(parsed, dict):
                return self._normalize_success(parsed)
            return self._fallback_success(text, FALLBACK_NOTE)
        except ModuleNotFoundError:
            return self._error_result(DEFAULT_ERROR_MESSAGE)
        except Exception as exc:
            return self._fallback_success(text, f"AI 连接异常 ({type(exc).__name__})，已切换规则兜底。")
