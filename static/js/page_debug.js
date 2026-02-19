// JS_VERSION: 20260216_1
(function () {
  var pageMeta = document.querySelector('meta[name="page-debug"]');
  var routeMeta = document.querySelector('meta[name="page-debug-route"]');
  var templateMeta = document.querySelector('meta[name="page-debug-template"]');
  var apiMeta = document.querySelector('meta[name="page-debug-api"]');
  var staticMeta = document.querySelector('meta[name="static-version"]');

  var payload = {
    page: pageMeta ? String(pageMeta.content || '').trim() : '-',
    route: routeMeta ? String(routeMeta.content || '').trim() : '-',
    template: templateMeta ? String(templateMeta.content || '').trim() : '-',
    api: apiMeta ? String(apiMeta.content || '').trim() : '-',
    static_version: staticMeta ? String(staticMeta.content || '').trim() : '-',
    js_version: '20260216_1'
  };

  window.__PAGE_DEBUG__ = payload;
  if (window.console && typeof window.console.info === 'function') {
    window.console.info('[PAGE_DEBUG]', payload);
  }
})();
