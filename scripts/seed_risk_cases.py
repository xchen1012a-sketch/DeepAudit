# -*- coding: utf-8 -*-
"""
风险案例数据生成脚本
生成 15-25 条风险案例，30% 来自风险事件升级，70% 独立创建
"""
import os
import sys
import io
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path

# 设置 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 案例状态
CASE_STATUSES = ["OPEN", "IN_PROGRESS", "CLOSED"]

# 状态分布：40-50% 已关闭
STATUS_DISTRIBUTION = ["OPEN"] * 20 + ["IN_PROGRESS"] * 35 + ["CLOSED"] * 45

# 处理结果
RESOLUTION_NOTES = {
    "CLOSED": [
        "经核实，发票真实有效，已批准报销",
        "供应商资质已补充完整，风险解除",
        "金额异常已说明，属于正常业务支出",
        "重复报销已拦截，已退回申请人",
        "合规问题已整改，流程已完善",
        "经审批，特殊情况予以通过",
        "发票信息已更正，重新提交审批",
        "供应商已更换，风险消除",
    ],
    "IN_PROGRESS": [
        "正在核实发票真伪",
        "等待供应商补充资料",
        "已联系申请人说明情况",
        "正在走特殊审批流程",
        "等待部门经理审批",
    ],
    "OPEN": [
        None,  # 新建案例无处理记录
    ]
}


def get_db_connection():
    """获取数据库连接"""
    db_path = os.path.join(PROJECT_ROOT, 'database.db')
    return sqlite3.connect(db_path)


def load_risk_events():
    """加载风险事件数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, risk_level, risk_score, created_at FROM risk_events")
    events = cursor.fetchall()
    conn.close()
    return events


def load_users():
    """加载用户数据"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, employee_name FROM users")
    users = cursor.fetchall()
    conn.close()
    return users


def generate_risk_cases(count=20):
    """生成风险案例数据"""
    print("=" * 80)
    print("风险案例数据生成脚本")
    print("=" * 80)
    print()
    
    # 加载风险事件数据
    print("[1/5] 加载风险事件数据...")
    risk_events = load_risk_events()
    if not risk_events:
        print("  [错误] 未找到风险事件数据，请先运行 seed_risk_events.py")
        return False
    print(f"  [OK] 加载了 {len(risk_events)} 条风险事件")
    print()
    
    # 加载用户数据
    print("[2/5] 加载用户数据...")
    users = load_users()
    if not users:
        print("  [警告] 未找到用户数据，将使用默认用户")
        users = [(1, "admin01", "系统管理员")]
    print(f"  [OK] 加载了 {len(users)} 个用户")
    print()
    
    # 连接数据库
    print("[3/5] 连接数据库...")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 检查现有风险案例数量
    cursor.execute("SELECT COUNT(*) FROM risk_cases")
    existing_count = cursor.fetchone()[0]
    print(f"  [OK] 当前风险案例数量: {existing_count} 条")
    print()
    
    # 生成风险案例
    print(f"[4/5] 生成 {count} 条风险案例数据...")
    risk_cases = []
    
    # 30% 来自风险事件升级（选择高风险事件）
    event_based_count = int(count * 0.3)
    independent_count = count - event_based_count
    
    # 从高风险事件中选择
    high_risk_events = [e for e in risk_events if e[1] in ["HIGH", "MEDIUM"]]
    if len(high_risk_events) < event_based_count:
        # 如果高风险事件不够，从所有事件中选择
        selected_events = random.sample(risk_events, min(event_based_count, len(risk_events)))
    else:
        selected_events = random.sample(high_risk_events, event_based_count)
    
    # 生成基于风险事件的案例
    for event_id, risk_level, risk_score, event_created_at in selected_events:
        status = random.choice(STATUS_DISTRIBUTION)
        assigned_user = random.choice(users)
        
        # 创建时间（在事件创建后 1-7 天）
        event_date = datetime.strptime(event_created_at, '%Y-%m-%d %H:%M:%S')
        created_at = event_date + timedelta(days=random.randint(1, 7))
        
        # 关闭时间（如果已关闭）
        if status == "CLOSED":
            closed_at = created_at + timedelta(days=random.randint(1, 30))
        else:
            closed_at = None
        
        # 处理记录
        resolution_note = random.choice(RESOLUTION_NOTES[status])
        
        risk_case = {
            "event_id": event_id,
            "assigned_to": assigned_user[1],  # username
            "status": status,
            "resolution_note": resolution_note,
            "created_at": created_at.strftime('%Y-%m-%d %H:%M:%S'),
            "closed_at": closed_at.strftime('%Y-%m-%d %H:%M:%S') if closed_at else None,
        }
        
        risk_cases.append(risk_case)
    
    # 生成独立案例（不关联风险事件，使用未使用的事件ID）
    # 获取未使用的事件ID
    used_event_ids = {case['event_id'] for case in risk_cases}
    available_events = [e for e in risk_events if e[0] not in used_event_ids]
    
    if len(available_events) < independent_count:
        print(f"  [警告] 可用事件不足，将生成 {len(available_events)} 个独立案例")
        independent_count = len(available_events)
    
    for i in range(independent_count):
        # 选择一个未使用的事件ID
        event = available_events.pop(random.randint(0, len(available_events) - 1))
        event_id = event[0]
        
        status = random.choice(STATUS_DISTRIBUTION)
        assigned_user = random.choice(users)
        
        # 创建时间
        created_at = datetime.now() - timedelta(days=random.randint(0, 90))
        
        # 关闭时间（如果已关闭）
        if status == "CLOSED":
            closed_at = created_at + timedelta(days=random.randint(1, 30))
        else:
            closed_at = None
        
        # 处理记录
        resolution_note = random.choice(RESOLUTION_NOTES[status])
        
        risk_case = {
            "event_id": event_id,
            "assigned_to": assigned_user[1],  # username
            "status": status,
            "resolution_note": resolution_note,
            "created_at": created_at.strftime('%Y-%m-%d %H:%M:%S'),
            "closed_at": closed_at.strftime('%Y-%m-%d %H:%M:%S') if closed_at else None,
        }
        
        risk_cases.append(risk_case)
    
    print(f"  [OK] 生成完成 (事件升级: {event_based_count}, 独立创建: {independent_count})")
    print()
    
    # 插入数据库
    print("[5/5] 插入数据库...")
    
    insert_sql = """
    INSERT INTO risk_cases (
        event_id, assigned_to, status, resolution_note, created_at, closed_at
    ) VALUES (
        :event_id, :assigned_to, :status, :resolution_note, :created_at, :closed_at
    )
    """
    
    try:
        cursor.executemany(insert_sql, risk_cases)
        conn.commit()
        print(f"  [OK] 成功插入 {len(risk_cases)} 条风险案例数据")
    except Exception as e:
        conn.rollback()
        print(f"  [错误] 插入失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()
    
    # 统计信息
    print()
    print("=" * 80)
    print("生成统计")
    print("=" * 80)
    
    # 按状态统计
    status_stats = {}
    for case in risk_cases:
        status_stats[case['status']] = status_stats.get(case['status'], 0) + 1
    
    print("\n案例状态分布:")
    for status, count in sorted(status_stats.items()):
        print(f"  {status:15} {count:3} 条 ({count/len(risk_cases)*100:.1f}%)")
    
    # 关闭率
    closed_count = status_stats.get('CLOSED', 0)
    close_rate = closed_count / len(risk_cases) * 100
    print(f"\n关闭率: {close_rate:.1f}%")
    
    # 按处理人统计
    assignee_stats = {}
    for case in risk_cases:
        assignee_stats[case['assigned_to']] = assignee_stats.get(case['assigned_to'], 0) + 1
    
    print("\n处理人分布:")
    for assignee, count in sorted(assignee_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {assignee:20} {count:3} 条 ({count/len(risk_cases)*100:.1f}%)")
    
    # 处理时长统计（已关闭案例）
    closed_cases = [c for c in risk_cases if c['status'] == 'CLOSED' and c['closed_at']]
    if closed_cases:
        durations = []
        for case in closed_cases:
            created = datetime.strptime(case['created_at'], '%Y-%m-%d %H:%M:%S')
            closed = datetime.strptime(case['closed_at'], '%Y-%m-%d %H:%M:%S')
            duration = (closed - created).days
            durations.append(duration)
        
        print(f"\n处理时长统计（已关闭案例）:")
        print(f"  平均处理时长: {sum(durations)/len(durations):.1f} 天")
        print(f"  最短处理时长: {min(durations)} 天")
        print(f"  最长处理时长: {max(durations)} 天")
    
    print()
    print("=" * 80)
    print("[OK] 风险案例数据生成完成！")
    print("=" * 80)
    
    return True


if __name__ == '__main__':
    try:
        success = generate_risk_cases(count=20)
        if success:
            print("\n✓ 脚本执行成功")
        else:
            print("\n✗ 脚本执行失败")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n[中断] 用户取消操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[错误] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

