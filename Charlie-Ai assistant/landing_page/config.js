/**
 * CHARLIE AI Public Web Configuration
 * Centralized environment-aware API and cloud service resolution.
 */
(function (root) {
  const hostname = window.location.hostname;
  const isLocal =
    hostname === 'localhost' ||
    hostname === '127.0.0.1' ||
    hostname === '0.0.0.0' ||
    window.location.protocol === 'file:';

  // Real production backend existence status:
  // Empirical check: api.charlie.ai is not yet provisioned in DNS.
  // In local development, licensing server runs on 127.0.0.1:8400.
  const isBackendDeployed = isLocal;

  const CharlieConfig = {
    isLocal: isLocal,
    isBackendLive: isBackendDeployed,
    // Production API endpoint when deployed; local proxy during dev
    apiBaseUrl: isLocal ? 'http://127.0.0.1:8400' : 'https://api.charlie.ai',
    version: '1.2.4',
    installerUrl:
      'https://github.com/cbasheer74-gif/charlie-ai-assistant/releases/download/v1.2.4/Charlie-AI-Desktop-1.2.4-Setup.exe',
    installerSha256:
      'd4d99628fa47f416da2c17a9ce3d3d24c9549e2c68bf97e1080dcbb70d62acbf'
  };

  root.CharlieConfig = CharlieConfig;
})(typeof window !== 'undefined' ? window : this);
