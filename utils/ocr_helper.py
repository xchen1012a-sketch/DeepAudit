# utils/ocr_helper.py
# -*- coding: utf-8 -*-

import base64
import os
from typing import Any, Dict

import dashscope
from dashscope import MultiModalConversation


def _img_to_b64_url(image_path: str) -> str:
    """将图片转换为 base64 data URL"""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    
    with open(image_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode("utf-8")
    
    # 根据文件扩展名确定 MIME 类型
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    mime_type = mime_map.get(ext, "image/jpeg")
    
    return f"data:{mime_type};base64,{img_data}"


def recognize_invoice(image_path: str) -> Dict[str, Any]:
    """
    使用阿里云百炼平台识别发票
    """
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing DASHSCOPE_API_KEY in environment variables.")
    
    dashscope.api_key = api_key
    
    try:
        # 将图片转换为 base64 URL
        image_url = _img_to_b64_url(image_path)
        
        # 调用阿里云百炼多模态对话 API
        messages = [
            {
                "role": "user",
                "content": [
                    {"image": image_url},
                    {
                        "text": """请识别这张发票/票据的信息，并以JSON格式返回以下字段：
- invoice_code: 发票代码
- invoice_number: 发票号码
- invoice_date: 开票日期 (格式: YYYY-MM-DD)
- amount: 金额/价税合计
- seller_name: 销售方名称
- buyer_name: 购买方名称
- tax_amount: 税额

如果是测试票据或报销单，请提取对应的编号、日期、金额等信息。
请只返回JSON，不要其他说明文字。"""
                    }
                ]
            }
        ]
        
        response = MultiModalConversation.call(
            model="qwen-vl-max",
            messages=messages
        )
        
        if response.status_code == 200:
            # 提取识别结果
            result_text = response.output.choices[0].message.content[0]["text"]
            
            # 尝试解析 JSON
            import json
            import re
            
            # 提取 JSON 部分（可能包含在 markdown 代码块中）
            json_match = re.search(r'```json\s*(.*?)\s*```', result_text, re.DOTALL)
            if json_match:
                result_text = json_match.group(1)
            else:
                # 尝试提取纯 JSON
                json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                if json_match:
                    result_text = json_match.group(0)
            
            try:
                ocr_data = json.loads(result_text)
            except:
                # 如果解析失败，返回原始文本
                ocr_data = {"raw_text": result_text}
            
            return {
                "mode": "dashscope_ocr",
                "status": "success",
                "data": ocr_data,
                "raw_response": result_text
            }
        else:
            return {
                "mode": "dashscope_ocr",
                "status": "error",
                "error_code": response.code,
                "error_message": response.message,
            }
    
    except Exception as e:
        return {
            "mode": "dashscope_ocr",
            "status": "error",
            "error": str(e),
        }
