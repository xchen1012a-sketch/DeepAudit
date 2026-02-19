"""
数据库自检：连接当前配置数据库，打印表名列表并统计 invoices 记录数。
运行：python scripts/db_smoke.py
"""

from __future__ import annotations

import os
import sqlite3

from utils.db import DB_PATH, init_db


def main() -> None:
    # 确保表结构存在（首次运行时需要建表）
    init_db()

    db_path = os.path.abspath(DB_PATH)
    print(f"[db_smoke] db_path={db_path}")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
        tables = [name for name in tables if name != "sqlite_sequence"]
        print(f"[db_smoke] tables={', '.join(tables)}")

        try:
            count = cur.execute("SELECT COUNT(1) FROM invoices").fetchone()[0]
        except Exception:
            count = 0
        print(f"[db_smoke] invoices_count={int(count)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
