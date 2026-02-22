# integrations/real_tax_provider.py
# -*- coding: utf-8 -*-
"""
真实发票验真服务对接
支持多种税务服务商：国家税务总局、百望云、航天信息等
"""

import hashlib
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict
from uuid import uuid4

import requests


class RealTaxProvider(ABC):
    """真实税务验真服务基类"""
    
    @abstractmethod
    def verify_invoice(
        self,
        invoice_code: str,
        invoice_number: str,
        invoice_date: str,
        amount: str,
        check_code: str = "",  # 校验码（后6位）
    ) -> Dict[str, Any]:
        """
        验真发票
        
        返回格式:
        {
            "provider": str,              # 服务商名称
            "request_id": str,            # 请求ID
            "status_code": int,           # HTTP状态码
            "latency_ms": int,            # 响应时间(毫秒)
            "result_status": str,         # PASSED/FAILED
            "result_code": str,           # 结果代码
            "result_message": str,        # 结果说明
            "invoice_status": str,        # 发票状态: NORMAL/VOID/RED/ABNORMAL
            "invoice_data": dict,         # 发票详细信息
            "raw_payload": dict,          # 原始响应
        }
        """
        pass


class NationalTaxProvider(RealTaxProvider):
    """
    国家税务总局发票查验平台
    官网: https://inv-veri.chinatax.gov.cn/
    
    注意：该平台有访问限制，建议通过第三方服务商对接
    """
    
    VERIFY_URL = "https://inv-veri.chinatax.gov.cn/index.html"
    
    def __init__(self):
        self.provider_name = "国家税务总局"
        self.session = requests.Session()
    
    def verify_invoice(
        self,
        invoice_code: str,
        invoice_number: str,
        invoice_date: str,
        amount: str,
        check_code: str = "",
    ) -> Dict[str, Any]:
        """
        国税总局验真接口
        
        限制：
        - 每天每张发票最多查询5次
        - 需要图形验证码
        - 有IP访问频率限制
        """
        request_id = str(uuid4())
        start_time = time.time()
        
        # 实际对接需要处理验证码、Cookie等
        # 这里仅作示例
        
        return {
            "provider": self.provider_name,
            "request_id": request_id,
            "status_code": 200,
            "latency_ms": int((time.time() - start_time) * 1000),
            "result_status": "FAILED",
            "result_code": "NOT_IMPLEMENTED",
            "result_message": "国税总局接口需要验证码，建议使用第三方服务商",
            "invoice_status": "UNKNOWN",
            "invoice_data": {},
            "raw_payload": {},
        }


class BaiWangProvider(RealTaxProvider):
    """
    百望云发票验真服务
    官网: https://www.baiwang.com/
    
    优势：
    - 直连税务系统
    - 无查询次数限制
    - 响应速度快
    - 支持批量查询
    """
    
    API_URL = "https://api.baiwang.com/invoice/verify"
    
    def __init__(self):
        self.provider_name = "百望云"
        self.app_key = os.getenv("BAIWANG_APP_KEY", "")
        self.app_secret = os.getenv("BAIWANG_APP_SECRET", "")
    
    def _generate_signature(self, params: dict) -> str:
        """生成签名"""
        sorted_params = sorted(params.items())
        sign_str = "&".join([f"{k}={v}" for k, v in sorted_params])
        sign_str = f"{sign_str}&key={self.app_secret}"
        return hashlib.md5(sign_str.encode()).hexdigest().upper()
    
    def verify_invoice(
        self,
        invoice_code: str,
        invoice_number: str,
        invoice_date: str,
        amount: str,
        check_code: str = "",
    ) -> Dict[str, Any]:
        """
        百望云验真接口
        
        参数：
        - invoice_code: 发票代码
        - invoice_number: 发票号码
        - invoice_date: 开票日期 (YYYYMMDD)
        - amount: 金额（不含税）
        - check_code: 校验码后6位
        """
        request_id = str(uuid4())
        start_time = time.time()
        
        if not self.app_key or not self.app_secret:
            return {
                "provider": self.provider_name,
                "request_id": request_id,
                "status_code": 401,
                "latency_ms": 0,
                "result_status": "FAILED",
                "result_code": "MISSING_CREDENTIALS",
                "result_message": "缺少百望云API密钥配置",
                "invoice_status": "UNKNOWN",
                "invoice_data": {},
                "raw_payload": {},
            }
        
        # 构建请求参数
        params = {
            "app_key": self.app_key,
            "invoice_code": invoice_code,
            "invoice_number": invoice_number,
            "invoice_date": invoice_date.replace("-", ""),
            "amount": amount,
            "check_code": check_code,
            "timestamp": str(int(time.time())),
            "nonce": str(uuid4()).replace("-", ""),
        }
        
        # 生成签名
        params["sign"] = self._generate_signature(params)
        
        try:
            response = requests.post(
                self.API_URL,
                json=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # 解析响应
            if data.get("code") == 0:
                invoice_info = data.get("data", {})
                invoice_status = invoice_info.get("status", "UNKNOWN")
                
                # 判断验真结果
                if invoice_status == "NORMAL":
                    result_status = "PASSED"
                    result_message = "发票验真通过"
                elif invoice_status == "VOID":
                    result_status = "FAILED"
                    result_message = "发票已作废"
                elif invoice_status == "RED":
                    result_status = "FAILED"
                    result_message = "发票已红冲"
                else:
                    result_status = "FAILED"
                    result_message = f"发票状态异常: {invoice_status}"
                
                return {
                    "provider": self.provider_name,
                    "request_id": request_id,
                    "status_code": 200,
                    "latency_ms": latency_ms,
                    "result_status": result_status,
                    "result_code": invoice_status,
                    "result_message": result_message,
                    "invoice_status": invoice_status,
                    "invoice_data": invoice_info,
                    "raw_payload": data,
                }
            else:
                return {
                    "provider": self.provider_name,
                    "request_id": request_id,
                    "status_code": 200,
                    "latency_ms": latency_ms,
                    "result_status": "FAILED",
                    "result_code": str(data.get("code")),
                    "result_message": data.get("message", "验真失败"),
                    "invoice_status": "UNKNOWN",
                    "invoice_data": {},
                    "raw_payload": data,
                }
        
        except requests.RequestException as e:
            return {
                "provider": self.provider_name,
                "request_id": request_id,
                "status_code": 500,
                "latency_ms": int((time.time() - start_time) * 1000),
                "result_status": "FAILED",
                "result_code": "NETWORK_ERROR",
                "result_message": f"网络请求失败: {str(e)}",
                "invoice_status": "UNKNOWN",
                "invoice_data": {},
                "raw_payload": {},
            }


class HangTianProvider(RealTaxProvider):
    """
    航天信息发票验真服务
    官网: https://www.aisino.com/
    """
    
    API_URL = "https://api.aisino.com/invoice/verify"
    
    def __init__(self):
        self.provider_name = "航天信息"
        self.api_key = os.getenv("HANGTIAN_API_KEY", "")
    
    def verify_invoice(
        self,
        invoice_code: str,
        invoice_number: str,
        invoice_date: str,
        amount: str,
        check_code: str = "",
    ) -> Dict[str, Any]:
        """航天信息验真接口"""
        request_id = str(uuid4())
        
        if not self.api_key:
            return {
                "provider": self.provider_name,
                "request_id": request_id,
                "status_code": 401,
                "latency_ms": 0,
                "result_status": "FAILED",
                "result_code": "MISSING_CREDENTIALS",
                "result_message": "缺少航天信息API密钥配置",
                "invoice_status": "UNKNOWN",
                "invoice_data": {},
                "raw_payload": {},
            }
        
        # 实际对接逻辑
        # ...
        
        return {
            "provider": self.provider_name,
            "request_id": request_id,
            "status_code": 200,
            "latency_ms": 0,
            "result_status": "FAILED",
            "result_code": "NOT_IMPLEMENTED",
            "result_message": "航天信息接口待实现",
            "invoice_status": "UNKNOWN",
            "invoice_data": {},
            "raw_payload": {},
        }


def build_real_tax_provider(provider_type: str = "baiwang") -> RealTaxProvider:
    """
    构建真实税务验真服务
    
    Args:
        provider_type: 服务商类型
            - "national": 国家税务总局（不推荐，有限制）
            - "baiwang": 百望云（推荐）
            - "hangtian": 航天信息
    """
    provider_map = {
        "national": NationalTaxProvider,
        "baiwang": BaiWangProvider,
        "hangtian": HangTianProvider,
    }
    
    provider_class = provider_map.get(provider_type.lower(), BaiWangProvider)
    return provider_class()


# 使用示例
if __name__ == "__main__":
    # 示例：使用百望云验真
    provider = build_real_tax_provider("baiwang")
    
    result = provider.verify_invoice(
        invoice_code="044031900111",
        invoice_number="12345678",
        invoice_date="2024-01-15",
        amount="1000.00",
        check_code="123456",
    )
    
    print(f"验真结果: {result['result_status']}")
    print(f"发票状态: {result['invoice_status']}")
    print(f"说明: {result['result_message']}")


