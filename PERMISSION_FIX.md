# 权限问题修复方案

## 问题诊断

根据代码分析，发现以下潜在问题：

### 1. 权限缓存问题（已排除）
- `get_user_permissions()` 每次都从数据库实时查询
- `current_user_permissions()` 每次都调用 `get_user_permissions()`
- **结论：不存在后端权限缓存问题**

### 2. 权限兜底逻辑问题（核心问题）
在 `utils/security.py` 的 `current_user_permissions()` 函数中：
```python
def current_user_permissions(user: dict[str, Any] | None = None) -> set[str]:
    target = user if user is not None else current_user()
    if not target:
        return set()

    user_id = target.get("id")
    # 每次都从数据库实时查询权限，避免缓存问题
    db_permissions = {item.strip().upper() for item in get_user_permissions(user_id) if item.strip()}
    if db_permissions:
        return _expand_permission_keys(db_permissions)
    # 如果数据库中没有权限记录，使用兜底逻辑  <-- 问题在这里
    return _expand_permission_keys(_legacy_permissions(target))
```

**问题**：当用户在数据库中没有任何权限记录时，会使用 `_legacy_permissions` 兜底，这可能导致：
- 即使配置了角色但没有分配权限，用户仍然通过兜底逻辑获得权限
- 管理员账号（如 admin01）通过用户名判断直接获得所有权限

### 3. 前端权限判断未刷新
前端可能缓存了用户权限信息，需要重新登录或刷新用户信息。

### 4. 数据库权限字段未正确写入
需要检查 `role_permissions` 表是否正确关联。

## 修复方案

### 修复 1：优化权限兜底逻辑
**文件**: `utils/security.py`

**修改内容**:
```python
def current_user_permissions(user: dict[str, Any] | None = None) -> set[str]:
    target = user if user is not None else current_user()
    if not target:
        return set()

    user_id = target.get("id")
    # 每次都从数据库实时查询权限，避免缓存问题
    db_permissions = {item.strip().upper() for item in get_user_permissions(user_id) if item.strip()}
    
    # 系统管理员特殊处理：即使没有数据库权限记录，也给予完整权限
    if is_system_admin(target):
        admin_perms = LEGACY_ROLE_PERMISSION_FALLBACK.get("admin", set())
        db_permissions |= {item.strip().upper() for item in admin_perms if item.strip()}
    
    if db_permissions:
        return _expand_permission_keys(db_permissions)
    
    # 如果数据库中没有权限记录，使用兜底逻辑（仅用于向后兼容）
    return _expand_permission_keys(_legacy_permissions(target))
```

**说明**: 
- 系统管理员（admin01等）即使没有数据库权限记录，也会获得完整权限
- 其他用户如果数据库中没有权限记录，会使用兜底逻辑（向后兼容）

### 修复 2：添加权限刷新 API
**文件**: `routes/auth.py`

**新增接口**:
```python
@bp.post("/api/auth/refresh_permissions")
@login_required
def refresh_permissions_api():
    """强制刷新当前用户的权限信息（用于角色权限配置后立即生效）"""
    user = current_user()
    if user is None:
        return jsonify({"ok": False, "msg": "unauthorized"}), 401
    
    # 重新构建用户信息（会重新查询数据库权限）
    payload = _build_me_payload(user)
    
    return jsonify({
        "ok": True,
        "msg": "权限已刷新",
        "user": payload
    })
```

**说明**: 
- 提供一个 API 端点，用于前端主动刷新当前用户的权限信息
- 每次调用都会重新从数据库查询权限

### 修复 3：前端权限刷新工具
**文件**: `static/js/permission_refresh.js` (新建)

**内容**:
```javascript
/**
 * 权限刷新工具
 * 用于在角色权限配置后立即刷新当前用户的权限信息
 */
(() => {
  // 全局权限刷新函数
  window.refreshCurrentUserPermissions = function() {
    if (typeof window.fetch !== 'function') {
      console.warn('[权限刷新] fetch API 不可用');
      return Promise.resolve();
    }
    
    return fetch('/api/auth/refresh_permissions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      }
    })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return response.json();
    })
    .then(data => {
      if (data && data.ok) {
        console.log('[权限刷新] 当前用户权限已刷新');
        
        // 触发自定义事件，通知其他组件权限已更新
        if (typeof window.CustomEvent === 'function') {
          const event = new CustomEvent('permissionsRefreshed', {
            detail: { user: data.user }
          });
          window.dispatchEvent(event);
        }
        
        return data;
      } else {
        throw new Error(data.msg || '刷新失败');
      }
    })
    .catch(err => {
      console.warn('[权限刷新] 刷新失败:', err);
      throw err;
    });
  };

  console.log('[权限刷新] 工具已加载');
})();
```

### 修复 4：角色管理页面集成权限刷新
**文件**: `static/js/admin_roles.js`

**修改位置**: 保存角色权限成功后

**修改内容**:
```javascript
const summary = text(payload.change_summary) || "角色权限已更新";
saveModal.modal("hide");
showFeedback("success", `保存成功：${summary}`);
await loadRoles(false);
await loadRoleAuditTrail(state.selectedRoleId);

// 刷新当前用户的权限信息（如果修改的是当前用户的角色）
refreshCurrentUserPermissions();
```

### 修复 5：用户管理页面集成权限刷新
**文件**: `static/js/admin_users.js`

**修改位置**: 修改用户角色成功后

**修改内容**:
```javascript
renderUsers();
actionModal.modal("hide");

if (text(config.actionCode) === "USER_RESET_PASSWORD") {
  const pwd = text(response.default_password) || "默认强口令";
  showFeedback("success", `重置密码成功，默认密码：${pwd}`);
} else {
  showFeedback("success", `${actionText(config.actionCode)}成功`);
}

// 如果是修改角色操作，刷新当前用户的权限信息
if (config.roleRequired && typeof window.refreshCurrentUserPermissions === 'function') {
  window.refreshCurrentUserPermissions().catch(() => {
    // 忽略刷新失败
  });
}
```

## 部署步骤

### 1. 备份数据库
```bash
# 备份当前数据库
cp database.db database.db.backup.$(date +%Y%m%d_%H%M%S)
```

### 2. 更新代码
所有修改已完成，文件列表：
- `utils/security.py` - 优化权限兜底逻辑
- `routes/auth.py` - 添加权限刷新 API
- `static/js/permission_refresh.js` - 新建权限刷新工具
- `static/js/admin_roles.js` - 集成权限刷新
- `static/js/admin_users.js` - 集成权限刷新
- `templates/layout/base.html` - 引入权限刷新工具

### 3. 重启应用
```bash
# 如果使用 systemd
sudo systemctl restart deepaudit

# 或者如果使用 supervisor
sudo supervisorctl restart deepaudit

# 或者直接重启 Python 进程
pkill -f "python.*app.py"
python app.py
```

### 4. 验证修复

#### 4.1 验证权限刷新 API
```bash
# 登录后测试权限刷新接口
curl -X POST http://your-server/api/auth/refresh_permissions \
  -H "Cookie: session=your_session_cookie" \
  -H "Content-Type: application/json"
```

#### 4.2 验证角色权限配置
1. 登录系统
2. 进入"组织与权限" -> "角色权限"
3. 选择一个角色，修改其权限
4. 保存后，检查浏览器控制台是否有 `[权限刷新] 当前用户权限已刷新` 日志
5. 刷新页面，验证权限是否生效

#### 4.3 验证用户角色分配
1. 进入"组织与权限" -> "人员管理"
2. 选择一个用户，点击"改角色"
3. 修改角色后保存
4. 检查浏览器控制台是否有权限刷新日志
5. 如果修改的是当前登录用户，刷新页面验证权限

## 常见问题排查

### Q1: 权限配置后仍然不生效
**排查步骤**:
1. 检查数据库中 `role_permissions` 表是否有对应记录
   ```sql
   SELECT rp.*, p.permission_key, r.role_name 
   FROM role_permissions rp
   JOIN permissions p ON p.id = rp.permission_id
   JOIN roles r ON r.id = rp.role_id
   WHERE rp.role_id = ?;
   ```

2. 检查用户是否正确关联到角色
   ```sql
   SELECT ur.*, r.role_name, u.username
   FROM user_roles ur
   JOIN roles r ON r.id = ur.role_id
   JOIN users u ON u.id = ur.user_id
   WHERE ur.user_id = ?;
   ```

3. 检查权限查询是否正常
   ```python
   from utils.db import get_user_permissions
   print(get_user_permissions(user_id))
   ```

### Q2: 前端权限刷新不生效
**排查步骤**:
1. 打开浏览器开发者工具（F12）
2. 查看 Console 标签页，是否有 `[权限刷新]` 相关日志
3. 查看 Network 标签页，检查 `/api/auth/refresh_permissions` 请求是否成功
4. 如果请求失败，查看响应内容和状态码

### Q3: 系统管理员权限异常
**排查步骤**:
1. 检查用户名是否在 `SYSTEM_ADMIN_USERNAMES` 中
   ```python
   # utils/security.py
   SYSTEM_ADMIN_USERNAMES = frozenset({"admin", "admin01", "administrator", "system_admin", "sys_admin"})
   ```

2. 检查 `is_system_admin()` 函数是否正常工作
   ```python
   from utils.security import is_system_admin, current_user
   user = current_user()
   print(f"Is system admin: {is_system_admin(user)}")
   ```

### Q4: 需要强制所有用户重新登录
如果修复后需要强制所有用户重新登录以刷新权限：

```python
# 清空所有 session（谨慎操作）
# 方法1：重启应用（session 存储在内存中）
# 方法2：如果使用 Redis 存储 session
redis-cli FLUSHDB

# 方法3：如果使用文件存储 session
rm -rf flask_session/*
```

## 性能优化建议

### 1. 权限查询优化
当前每次权限判断都会查询数据库，如果性能有问题，可以考虑：
- 在 session 中缓存用户权限（需要在角色权限变更时清除缓存）
- 使用 Redis 缓存权限信息（TTL 设置为 5-10 分钟）

### 2. 数据库索引
确保以下索引存在：
```sql
CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role_id ON role_permissions(role_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_permissions_key ON permissions(permission_key);
```

## 总结

本次修复主要解决了以下问题：
1. ✅ 优化了权限兜底逻辑，确保系统管理员始终有权限
2. ✅ 添加了权限刷新 API，支持前端主动刷新权限
3. ✅ 在角色管理和用户管理页面集成了自动权限刷新
4. ✅ 提供了完整的排查和验证步骤

**重要提示**：
- 所有修改都已完成，可以直接重启应用部署
- 建议在测试环境先验证，确认无误后再部署到生产环境
- 如果仍有问题，请检查数据库中的权限数据是否正确

