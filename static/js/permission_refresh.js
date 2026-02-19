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

  // 监听权限刷新事件，可选择性地重新加载页面或更新UI
  window.addEventListener('permissionsRefreshed', (event) => {
    console.log('[权限刷新] 权限已更新，用户信息:', event.detail);
    
    // 可以在这里添加UI更新逻辑
    // 例如：更新导航菜单、按钮状态等
  });

  console.log('[权限刷新] 工具已加载');
})();

