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

  function ApiClientError(code, message, status) {
    this.name = 'ApiClientError';
    this.code = code;
    this.message = message;
    this.status = status;
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
      try {
        var body = await response.json();
        code = (body.error && body.error.code) || code;
        message = (body.error && body.error.message) || '';
      } catch (parseError) { /* keep defaults */ }
      throw new ApiClientError(code, message, response.status);
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
  function errorMessage(err, lang) {
    var key = ERROR_KEYS[err && err.code] || 'error.generic';
    return lang ? I18N.tIn(lang, key) : I18N.t(key);
  }

  window.McpApi = {
    buildMcp: buildMcp,
    health: health,
    speakStatus: speakStatus,
    sendReceipt: sendReceipt,
    slugify: slugify,
    isValidServerName: isValidServerName,
    errorMessage: errorMessage
  };
})();
