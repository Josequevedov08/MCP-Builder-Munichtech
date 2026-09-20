/* Deployment settings. Local development needs no changes: api.js falls back to the local API. */
(function () {
  'use strict';

  var API_BY_HOST = {
    'mcp.quevedojose.com': 'https://mcp-api.quevedojose.com',
    'josequevedov08.github.io': 'https://mcp-api.quevedojose.com'
  };

  var base = API_BY_HOST[window.location.hostname];
  if (base) window.MCP_API_BASE = base;
})();
