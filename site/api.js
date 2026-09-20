/* Client for the MCP Builder API. Exposes window.McpApi. */
(function () {
  'use strict';

  // Same origin when the site is served by the API itself, local API otherwise.
  // Set window.MCP_API_BASE before loading this file to target a deployed API.
  var DEFAULT_BASE = window.location.port === '8000' ? '' : 'http://127.0.0.1:8000';
  var API_BASE = (window.MCP_API_BASE !== undefined ? window.MCP_API_BASE : DEFAULT_BASE).replace(/\/$/, '');

  var SERVER_NAME_RE = /^[a-z][a-z0-9-]{2,39}$/;
  var ERROR_KEYS = {
    network: 'error.network',
    invalid_request: 'error.invalid_request',
    model_timeout: 'error.model_timeout',
    model_busy: 'error.model_busy',
    rate_limited: 'error.model_busy',
    voice_unavailable: 'error.voice',
    voice_not_configured: 'error.voice',
    voice_timeout: 'error.voice',
    model_unavailable: 'error.model_unavailable',
    model_not_configured: 'error.model_unavailable',
    model_bad_output: 'error.model_bad_output'
  };

  function ApiClientError(code, message, status, fields) {
    this.name = 'ApiClientError';
    this.code = code;
    this.message = message;
    this.status = status;
    this.fields = fields || [];
  }
  ApiClientError.prototype = Object.create(Error.prototype);

  // Sends a JSON POST and returns the raw response. Errors are normalized to ApiClientError.
  async function post(path, payload) {
    var response;
    try {
      response = await fetch(API_BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } catch (networkError) {
      throw new ApiClientError('network', 'Network error', 0);
    }
    if (!response.ok) {
      var code = 'internal_error';
      var message = '';
      var fields = [];
      try {
        var body = await response.json();
        code = (body.error && body.error.code) || code;
        message = (body.error && body.error.message) || '';
        fields = (body.error && body.error.fields) || [];
      } catch (parseError) { /* keep defaults */ }
      throw new ApiClientError(code, message, response.status, fields);
    }
    return response;
  }

  // POST /api/build-mcp
  async function buildMcp(payload) {
    var response = await post('/api/build-mcp', payload);
    return response.json();
  }

  // POST /api/send-receipt. The server computes the amounts and attaches the generated server.
  async function sendReceipt(payload) {
    var response = await post('/api/send-receipt', payload);
    return response.json();
  }

  // Same error handling as post(), for GET requests.
  async function getJson(path, headers) {
    var response;
    try {
      response = await fetch(API_BASE + path, { headers: headers || {} });
    } catch (networkError) {
      throw new ApiClientError('network', 'Network error', 0);
    }
    if (!response.ok) {
      var code = 'internal_error';
      try {
        var body = await response.json();
        code = (body.error && body.error.code) || code;
      } catch (parseError) { /* keep defaults */ }
      throw new ApiClientError(code, '', response.status);
    }
    return response.json();
  }

  // GET /api/stats: public numbers about real usage, without personal data.
  function getStats() {
    return getJson('/api/stats');
  }

  // GET /api/admin/support: the support inbox, protected with the admin token.
  function getSupportInbox(token) {
    return getJson('/api/admin/support', { 'X-Admin-Token': token });
  }

  // POST /api/events/download. Counting a download must never disturb it.
  async function recordDownload(buildId) {
    try { await post('/api/events/download', { build_id: buildId }); } catch (error) { /* not important */ }
  }

  // POST /api/support
  async function sendSupport(payload) {
    var response = await post('/api/support', payload);
    return response.json();
  }

  var currentAudio = null;

  // POST /api/voice-status, then plays the returned MP3.
  async function speakStatus(payload) {
    var response = await post('/api/voice-status', payload);
    var url = URL.createObjectURL(await response.blob());
    if (currentAudio) currentAudio.pause();
    currentAudio = new Audio(url);
    currentAudio.addEventListener('ended', function () { URL.revokeObjectURL(url); });
    await currentAudio.play();
  }

  // GET /api/health. The deadline is long because a sleeping free-tier host needs time to wake up.
  async function health(timeoutMs) {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, timeoutMs || 75000);
    try {
      var response = await fetch(API_BASE + '/api/health', { signal: controller.signal });
      if (!response.ok) throw new ApiClientError('internal_error', '', response.status);
      return await response.json();
    } catch (error) {
      if (error instanceof ApiClientError) throw error;
      throw new ApiClientError('network', 'Network error', 0);
    } finally {
      clearTimeout(timer);
    }
  }

  // Turns free text such as "Shop DB" into "shop-db".
  function slugify(value) {
    return String(value || '')
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 40)
      .replace(/-+$/, '');
  }

  function isValidServerName(name) {
    return SERVER_NAME_RE.test(name);
  }

  // Localized, user-safe message for an error thrown by this client.
  // Pass a language code to get the message in a language other than the interface.
  var RESOURCE_CODES = ['tables_required', 'invalid_tables', 'endpoints_required', 'invalid_endpoints', 'invalid_folders'];

  // The same rules as the server, so the form can explain a problem before anything is sent.
  // Returns an error code, or null when the resources are fine.
  function validateResources(source, resources) {
    var list = resources || [];
    if (source === 'database') {
      if (!list.length) return 'tables_required';
      if (list.some(function (r) { return !/^[A-Za-z_][\w$]*(\.[A-Za-z_][\w$]*)?$/.test(r); })) return 'invalid_tables';
    } else if (source === 'api') {
      if (!list.length) return 'endpoints_required';
      if (list.some(function (r) { return r.indexOf('://') !== -1 || r.split('/').indexOf('..') !== -1 || !/^\/?[A-Za-z0-9._~\-\/{}:@%]+$/.test(r); })) return 'invalid_endpoints';
    } else if (list.some(function (r) { return r.split(/[\\/]/).indexOf('..') !== -1 || /^([A-Za-z]:)?[\\/]*$/.test(r); })) {
      return 'invalid_folders';
    }
    return null;
  }

  function errorMessage(err, lang) {
    // A specific reason from the server (for example a missing table) beats the generic text.
    var reason = err && err.fields && err.fields.map(function (f) { return f.message; }).filter(function (m) { return RESOURCE_CODES.indexOf(m) !== -1; })[0];
    var key = reason ? 'error.' + reason : ERROR_KEYS[err && err.code] || 'error.generic';
    return lang ? I18N.tIn(lang, key) : I18N.t(key);
  }

  window.McpApi = {
    buildMcp: buildMcp,
    health: health,
    speakStatus: speakStatus,
    getStats: getStats,
    getSupportInbox: getSupportInbox,
    recordDownload: recordDownload,
    sendSupport: sendSupport,
    sendReceipt: sendReceipt,
    slugify: slugify,
    validateResources: validateResources,
    isValidServerName: isValidServerName,
    errorMessage: errorMessage
  };
})();
