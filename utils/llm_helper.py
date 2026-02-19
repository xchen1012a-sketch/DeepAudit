# -*- coding: utf-8 -*-

from typing import Any, Dict, Optional

from utils.llm_audit import semantic_audit_report as _semantic_audit_report


def semantic_audit_report(
    ocr_text: str,
    claim_category: str = "office_expense",
    extra_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _semantic_audit_report(
        ocr_text=ocr_text,
        claim_category=claim_category,
        extra_context=extra_context,
    )
