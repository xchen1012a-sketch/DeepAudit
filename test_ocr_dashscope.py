#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试阿里云百炼OCR功能"""

import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.ocr_helper import recognize_invoice

def test_ocr():
    # 测试图片路径
    test_image = Path(__file__).parent / "uploads" / "test_receipt_with_fields_df578d79.png"
    
    if not test_image.exists():
        print(f"测试图片不存在: {test_image}")
        return
    
    print("=" * 60)
    print("测试阿里云百炼OCR识别")
    print("=" * 60)
    print(f"图片路径: {test_image}")
    print("\n正在识别...")
    
    try:
        result = recognize_invoice(str(test_image))
        
        print("\n识别结果:")
        print(f"模式: {result.get('mode')}")
        print(f"状态: {result.get('status')}")
        
        if result.get('status') == 'success':
            data = result.get('data', {})
            print("\n提取的字段:")
            print(f"  发票代码: {data.get('invoice_code', '未识别')}")
            print(f"  发票号码: {data.get('invoice_number', '未识别')}")
            print(f"  开票日期: {data.get('invoice_date', '未识别')}")
            print(f"  金额: {data.get('amount', '未识别')}")
            print(f"  销售方: {data.get('seller_name', '未识别')}")
            print(f"  购买方: {data.get('buyer_name', '未识别')}")
            print(f"  税额: {data.get('tax_amount', '未识别')}")
            
            print("\n原始响应:")
            print(result.get('raw_response', '')[:500])
        else:
            print(f"\n错误信息: {result.get('error_message') or result.get('error')}")
        
        print("\n" + "=" * 60)
        print("✓ OCR测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ OCR测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ocr()


