"""
测试审批修复：验证所有权限的人处理完单据后都能在"我已处理"中看到
"""
import sqlite3
from datetime import datetime

def check_approval_records():
    """检查数据库中的审批记录"""
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 60)
    print("审批记录检查")
    print("=" * 60)
    
    # 查询所有已处理的单据
    cursor.execute("""
        SELECT 
            id,
            reference_no,
            applicant,
            amount,
            risk_level,
            approval_status,
            approval_stage,
            first_approver_id,
            first_approved_at,
            second_approver_id,
            second_approved_at,
            queue_owner_id
        FROM invoices
        WHERE approval_status IN ('APPROVED', 'REJECTED', 'RETURNED')
        ORDER BY id DESC
        LIMIT 20
    """)
    
    rows = cursor.fetchall()
    
    if not rows:
        print("\n暂无已处理的审批记录")
    else:
        print(f"\n找到 {len(rows)} 条已处理记录：\n")
        for row in rows:
            print(f"单据ID: {row['id']}")
            print(f"  单据号: {row['reference_no']}")
            print(f"  申请人: {row['applicant']}")
            print(f"  金额: {row['amount']}")
            print(f"  风险等级: {row['risk_level']}")
            print(f"  审批状态: {row['approval_status']}")
            print(f"  审批阶段: {row['approval_stage']}")
            print(f"  一级审批人: {row['first_approver_id'] or '未设置'}")
            print(f"  一级审批时间: {row['first_approved_at'] or '未设置'}")
            print(f"  二级审批人: {row['second_approver_id'] or '未设置'}")
            print(f"  二级审批时间: {row['second_approved_at'] or '未设置'}")
            print(f"  当前处理人: {row['queue_owner_id'] or '无'}")
            print("-" * 60)
    
    # 统计各用户处理的单据数
    print("\n" + "=" * 60)
    print("各用户处理单据统计")
    print("=" * 60)
    
    cursor.execute("""
        SELECT 
            first_approver_id as approver,
            COUNT(*) as count
        FROM invoices
        WHERE first_approver_id IS NOT NULL AND first_approver_id != ''
        GROUP BY first_approver_id
        ORDER BY count DESC
    """)
    
    first_approvers = cursor.fetchall()
    if first_approvers:
        print("\n一级审批人统计：")
        for row in first_approvers:
            print(f"  {row['approver']}: {row['count']} 条")
    
    cursor.execute("""
        SELECT 
            second_approver_id as approver,
            COUNT(*) as count
        FROM invoices
        WHERE second_approver_id IS NOT NULL AND second_approver_id != ''
        GROUP BY second_approver_id
        ORDER BY count DESC
    """)
    
    second_approvers = cursor.fetchall()
    if second_approvers:
        print("\n二级审批人统计：")
        for row in second_approvers:
            print(f"  {row['approver']}: {row['count']} 条")
    
    conn.close()
    print("\n" + "=" * 60)

if __name__ == "__main__":
    check_approval_records()


