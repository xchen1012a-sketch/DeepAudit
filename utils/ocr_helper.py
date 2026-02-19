# utils/ocr_helper.py
# -*- coding: utf-8 -*-

import base64
import os
import time
from typing import Any, Dict

import requests

TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"

# 1) 增值税发票（模板类）
INVOICE_OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/vat_invoice"
# 2) 通用文字识别（兜底）
GENERAL_OCR_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"

_TOKEN_CACHE: Dict[str, Any] = {"access_token": None, "expires_at": 0}


def get_access_token() -> str:
    now = int(time.time())
    if _TOKEN_CACHE["access_token"] and now < _TOKEN_CACHE["expires_at"]:
        return _TOKEN_CACHE["access_token"]

    ocr_ak = os.getenv("BAIDU_OCR_AK", "").strip()
    ocr_sk = os.getenv("BAIDU_OCR_SK", "").strip()
    if not ocr_ak or not ocr_sk:
        raise RuntimeError("Missing BAIDU_OCR_AK/BAIDU_OCR_SK in environment variables.")

    params = {
        "grant_type": "client_credentials",
        "client_id": ocr_ak,
        "client_secret": ocr_sk,
    }
    resp = requests.get(TOKEN_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    access_token = data.get("access_token")
    expires_in = int(data.get("expires_in", 0))
    if not access_token:
        raise RuntimeError(f"Failed to get access_token: {data}")

    _TOKEN_CACHE["access_token"] = access_token
    _TOKEN_CACHE["expires_at"] = now + max(expires_in - 60, 0)
    return access_token


def _img_to_b64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def recognize_vat_invoice(image_path: str) -> Dict[str, Any]:
    """增值税发票识别（模板）"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    access_token = get_access_token()
    url = f"{INVOICE_OCR_URL}?access_token={access_token}"
    payload = {"image": _img_to_b64(image_path)}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    resp = requests.post(url, data=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def recognize_general_text(image_path: str) -> Dict[str, Any]:
    """通用文字识别（兜底）"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    access_token = get_access_token()
    url = f"{GENERAL_OCR_URL}?access_token={access_token}"
    payload = {"image": _img_to_b64(image_path)}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    resp = requests.post(url, data=payload, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


def recognize_invoice(image_path: str) -> Dict[str, Any]:
    """
    统一入口：先走 vat_invoice；若模板失败，则降级到 general_basic
    """
    vat = recognize_vat_invoice(image_path)

    # 百度返回模板失败：282103（你刚遇到的）
    if isinstance(vat, dict) and vat.get("error_code") == 282103:
        general = recognize_general_text(image_path)
        return {
            "mode": "general_fallback",
            "vat": vat,
            "general": general,
        }

    return {
        "mode": "vat_invoice",
        "vat": vat,
    }

# 自查点：
# 1) python -c "from utils.ocr_helper import get_access_token; print(get_access_token()[:10])" 仍然能出 token
# 2) recognize_invoice() 对测试图会返回 mode=general_fallback
