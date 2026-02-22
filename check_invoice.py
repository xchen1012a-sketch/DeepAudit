#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查发票验真问题"""

import json
from utils.db import get_conn

def check_invoice(reference_no):
    conn = get_conn()
    cursor = conn.execute(
        """
        SELECT id, reference_no, invoice_code, invoice_number, 
               amount, invoice_date, raw_json,
               verify_status, verify_message, verify_status_code
        FROM invoices 
        WHERE reference_no = ?
        """,
        (reference_no,)
    )
    row = cursor.fetchone()
    
    if not row:
        print(f"未找到单据: {reference_no}")
        return
    
    print("=" * 60)
    print(f"单据编号: {row[1]}")
    print(f"发票ID: {row[0]}")
    print(f"发票代码: {row[2] or '【空】'}")
    print(f"发票号码: {row[3] or '【空】'}")
    print(f"金额: {row[4] or '【空】'}")
    print(f"开票日期: {row[5] or '【空】'}")
    print(f"验真状态: {row[7] or '未验真'}")
    print(f"验真说明: {row[8] or '-'}")
    print(f"验真状态码: {row[9] or '-'}")
    print("=" * 60)
    
    if row[6]:
        try:
            raw_json = json.loads(row[6])
            print("\nRaw JSON 内容:")
            print(f"  mode: {raw_json.get('mode', '-')}")
            print(f"  entry_mode: {raw_json.get('entry_mode', '-')}")
            
            manual_entry = raw_json.get('manual_entry', {})
            if manual_entry:
                print("\n  manual_entry:")
                print(f"    invoice_code: {manual_entry.get('invoice_code', '【空】')}")
                print(f"    invoice_number: {manual_entry.get('invoice_number', '【空】')}")
                print(f"    seller_name: {manual_entry.get('seller_name', '【空】')}")
            
            # 检查其他可能的字段
            for key in ['invoice_code', 'invoiceCode', 'code', 'invoice_number', 'invoiceNo', 'number']:
                if key in raw_json:
                    print(f"  {key}: {raw_json[key]}")
        except Exception as e:
            print(f"\n解析 raw_json 失败: {e}")
    
    print("\n" + "=" * 60)
    print("问题诊断:")
    if not row[2] and not row[3]:
        print("❌ 发票代码和发票号码都为空！")
        print("   这会导致验真接口返回 400 错误")
        print("\n解决方案:")
        print("1. 在详情页面点击「补录」按钮")
        print("2. 填写发票代码和发票号码")
        print("3. 保存后重新点击「执行验真」")
    elif not row[2]:
        print("⚠️  发票代码为空")
    elif not row[3]:
        print("⚠️  发票号码为空")
    else:
        print("✓ 发票代码和号码都已填写")
    print("=" * 60)

if __name__ == "__main__":
    check_invoice("EXP-20260222-0001")


