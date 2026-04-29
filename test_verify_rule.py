#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试验真规则"""

from integrations.tax_provider import MockTaxProvider

provider = MockTaxProvider('TEST_PROVIDER')

# 测试1: TEST票据（应该通过）
result1 = provider.verify_invoice('TEST-1409-20260218', 'TEST-Rcpt-20260218-79801')
print("Test 1 - TEST ticket:")
print(f"  Status: {result1['result_status']}")
print(f"  Message: {result1['result_message']}")
print(f"  Code: {result1['status_code']}")
print()

# 测试2: 普通票据，最后一位是偶数（应该通过）
result2 = provider.verify_invoice('1234567890', '12345678')
print("Test 2 - Normal ticket (even):")
print(f"  Status: {result2['result_status']}")
print(f"  Message: {result2['result_message']}")
print(f"  Code: {result2['status_code']}")
print()

# 测试3: 普通票据，最后一位是奇数（应该失败）
result3 = provider.verify_invoice('1234567890', '12345679')
print("Test 3 - Normal ticket (odd):")
print(f"  Status: {result3['result_status']}")
print(f"  Message: {result3['result_message']}")
print(f"  Code: {result3['status_code']}")



