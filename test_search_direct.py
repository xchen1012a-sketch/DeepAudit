# -*- coding: utf-8 -*-
"""直接测试搜索逻辑"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.db import get_conn
from utils.security import can_access_approval_console

def test_search_logic(keyword):
    """测试搜索逻辑"""
    print(f"\n{'='*80}")
    print(f"测试搜索: {keyword}")
    print(f"{'='*80}\n")
    
    # 模拟用户
    user = {
        'id': 1,
        'username': 'admin01',
        'role': 'admin',
        'department': '财务部'
    }
    
    # 检查审批权限
    has_approval = can_access_approval_console(user)
    print(f"用户有审批权限: {has_approval}")
    
    # 如果有审批权限，scope 应该是 all_access
    if has_approval:
        scope = {"all_access": True}
        print("数据范围: 全部访问")
    else:
        scope = {"all_access": False, "department_names": [user['department']]}
        print(f"数据范围: 仅限部门 {user['department']}")
    
    # 构建 SQL
    like = f"%{keyword}%"
    exact_match = keyword.strip()
    
    # 构建 scope_sql
    if scope.get("all_access"):
        scope_sql = ""
        scope_params = []
    else:
        depts = scope.get("department_names", [])
        if depts:
            placeholders = ",".join("?" for _ in depts)
            scope_sql = f" AND department IN ({placeholders})"
            scope_params = depts
        else:
            scope_sql = ""
            scope_params = []
    
    sql = (
        "SELECT id, reference_no, filename, amount, department, applicant, "
        "risk_level, status, invoice_date, created_at, record_state, "
        "CASE "
        "  WHEN CAST(id AS TEXT) = ? THEN 1 "
        "  WHEN LOWER(COALESCE(reference_no,'')) = LOWER(?) THEN 2 "
        "  WHEN LOWER(COALESCE(reference_no,'')) LIKE LOWER(?) THEN 3 "
        "  WHEN LOWER(COALESCE(filename,'')) LIKE LOWER(?) THEN 4 "
        "  WHEN LOWER(COALESCE(applicant,'')) LIKE LOWER(?) THEN 5 "
        "  ELSE 6 "
        "END AS match_priority "
        "FROM invoices WHERE ("
        "  CAST(id AS TEXT) = ?"
        "  OR LOWER(COALESCE(reference_no,'')) = LOWER(?)"
        "  OR LOWER(COALESCE(reference_no,'')) LIKE LOWER(?)"
        "  OR LOWER(COALESCE(filename,'')) LIKE LOWER(?)"
        "  OR LOWER(COALESCE(applicant,'')) LIKE LOWER(?)"
        "  OR LOWER(COALESCE(department,'')) LIKE LOWER(?)"
        ")" + scope_sql + " ORDER BY match_priority ASC, id DESC LIMIT 10"
    )
    
    params = [
        exact_match, exact_match, like, like, like,  # match_priority计算
        exact_match, exact_match, like, like, like, like,  # WHERE条件
        *scope_params
    ]
    
    print(f"\nSQL: {sql}")
    print(f"参数: {params}\n")
    
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    
    if not rows:
        print("[结果] 没有找到匹配的单据")
    else:
        print(f"[结果] 找到 {len(rows)} 条匹配的单据：\n")
        for r in rows:
            print(f"  ID: {r['id']}")
            print(f"    reference_no: {r['reference_no']}")
            print(f"    department: {r['department']}")
            print(f"    record_state: {r['record_state']}")
            print(f"    match_priority: {r['match_priority']}")
            print()

if __name__ == "__main__":
    test_terms = [
        "EXP-20260222-0001",
        "EXP-20260222-0002",
        "EXP-20260219-0018"
    ]
    
    for term in test_terms:
        test_search_logic(term)



