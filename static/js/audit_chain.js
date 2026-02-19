/**
 * 智能审计链前端逻辑
 * 入口表单提交、链数据加载（可选）
 */
(function () {
  'use strict';

  var form = document.getElementById('auditChainEntryForm');
  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var ot = document.getElementById('entryObjectType');
      var oid = document.getElementById('entryObjectId');
      if (!ot || !oid) return;
      var typeVal = ot.value;
      var idVal = (oid.value || '').trim();
      if (!idVal) {
        alert('请输入对象 ID');
        return;
      }
      window.location.href = '/audit_chain/' + encodeURIComponent(typeVal) + '/' + encodeURIComponent(idVal);
    });
  }

  /**
   * 从 API 加载链数据（可用于动态刷新）
   * @param {string} objectType - invoice | risk_event | risk_case | approval
   * @param {string} objectId - 对象 ID
   * @returns {Promise<{ok: boolean, chain?: object, error?: object}>}
   */
  window.AuditChain = window.AuditChain || {};
  window.AuditChain.loadChain = function (objectType, objectId) {
    if (!objectType || !objectId) {
      return Promise.resolve({ ok: false, error: { message_cn: '参数无效' } });
    }
    return fetch('/api/audit_chain/' + encodeURIComponent(objectType) + '/' + encodeURIComponent(objectId), {
      method: 'GET',
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
    })
      .then(function (r) {
        return r.json().then(function (data) {
          if (!r.ok) {
            data.ok = false;
          }
          return data;
        });
      })
      .catch(function (err) {
        return { ok: false, error: { message_cn: '请求失败: ' + (err && err.message ? err.message : '未知错误') } };
      });
  };
})();
