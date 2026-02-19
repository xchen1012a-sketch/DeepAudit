# 数据库同步问题修复 - 快速参考

## 问题

网页写入的数据在 Navicat 中看不到。

## 原因

- Flask 写入：`database.db`（根目录）
- Navicat 打开：`exports/database_real_for_navicat.db`（静态副本）
- 两者不是同一个文件

## 解决方案（二选一）

### 方案 A：Navicat 直接打开真实库（推荐）

**步骤**：

1. 运行诊断找到真实库路径：
   ```bash
   python scripts\diagnose_db_path.py
   ```

2. 在 Navicat 中打开该路径（通常是 `C:\Users\画桦\Desktop\DeepAudit_Pro\database.db`）

3. **注意**：查看数据时需关闭 Flask 应用（SQLite 文件锁）

### 方案 B：使用导出副本（需手动同步）

**步骤**：

1. 每次需要查看最新数据时运行：
   ```bash
   python scripts\export_real_db.py
   ```

2. 在 Navicat 中刷新连接

3. **优点**：可以同时运行 Flask 和 Navicat

## 验证修复

```bash
python scripts\verify_db_write.py
```

## 启动应用（显示数据库路径）

```bash
python app.py
```

查看启动日志中的数据库路径信息。

## 一键修复工具

```bash
scripts\fix_db_sync.bat
```

会自动执行诊断、验证、导出三个步骤。

## 详细文档

参见：`docs/数据库同步问题修复指南.md`

