// Global API config & helpers
(() => {
  const API_BASE = window.API_BASE_URL || '/api';
  localStorage.removeItem('apiBaseUrl');

  const originalFetch = window.fetch.bind(window);

  // Lightweight status banner
  let statusBar = null;
  function ensureStatusBar() {
    if (statusBar) return statusBar;
    statusBar = document.createElement('div');
    statusBar.id = 'apiStatusBar';
    statusBar.style.position = 'fixed';
    statusBar.style.top = '12px';
    statusBar.style.right = '12px';
    statusBar.style.padding = '10px 14px';
    statusBar.style.borderRadius = '12px';
    statusBar.style.boxShadow = '0 8px 24px rgba(0,0,0,0.15)';
    statusBar.style.fontFamily = 'Inter, system-ui, -apple-system, sans-serif';
    statusBar.style.fontSize = '14px';
    statusBar.style.color = '#fff';
    statusBar.style.display = 'none';
    statusBar.style.zIndex = '9999';
    document.body.appendChild(statusBar);
    return statusBar;
  }

  function showStatus(message, tone = 'info') {
    const el = ensureStatusBar();
    const colors = {
      info: '#0ea5e9',
      success: '#22c55e',
      warning: '#eab308',
      danger: '#ef4444'
    };
    el.style.background = colors[tone] || colors.info;
    el.textContent = message;
    el.style.display = 'block';
    clearTimeout(el._timeout);
    el._timeout = setTimeout(() => { el.style.display = 'none'; }, 4500);
  }

  window.API_BASE = API_BASE;
  window.apiUrl = (path = '') => {
    if (!path) return API_BASE;
    if (/^https?:\/\//i.test(path)) return path;
    return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
  };
  window.rawFetch = originalFetch;
  window.setApiBaseUrl = (url) => {
    window.API_BASE_URL = url;
    return url;
  };
  window.apiStatus = { show: showStatus };

  window.fetch = async (input, init = {}) => {
    let url = typeof input === 'string' ? input : input.url;
    const opts = { ...init, headers: { ...(init.headers || {}) } };

    const apiPathPattern = /^\/(admin|users|teacher|catalogs|token|public)(\/|\?|$)/;
    const isLocalApiCall = typeof url === 'string'
      && /^https?:\/\/(?:localhost|127\.0\.0\.1):8000(?=\/|$)/i.test(url);
    const isRelativeApiCall = typeof url === 'string' && apiPathPattern.test(url);
    const isApiCall = isLocalApiCall || isRelativeApiCall;
    if (isApiCall) {
      url = isLocalApiCall
        ? url.replace(/^https?:\/\/(?:localhost|127\.0\.0\.1):8000/i, API_BASE)
        : window.apiUrl(url);
      input = url;
    }

    const token = localStorage.getItem('token');
    const hasAuthHeader = Object.keys(opts.headers).some(h => h.toLowerCase() === 'authorization');
    const shouldAttachToken = token && isApiCall && opts.auth !== false && !hasAuthHeader;
    if (shouldAttachToken) {
      opts.headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const response = await originalFetch(input, opts);
      if (isApiCall && response.status === 401 && token && opts.auth !== false) {
        localStorage.removeItem('token');
        const redirect = new URL('/login', window.location.origin);
        redirect.searchParams.set('reason', 'expired');
        showStatus('Sesión expirada. Ingresa de nuevo.', 'warning');
        window.top.location.href = redirect.toString();
      }
      if (!response.ok && response.status >= 500) {
        showStatus('Error del servidor. Intenta más tarde.', 'danger');
      }
      return response;
    } catch (err) {
      showStatus('No pudimos conectar con la API.', 'danger');
      throw err;
    }
  };
})();
