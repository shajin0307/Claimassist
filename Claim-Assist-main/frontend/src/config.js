// ============================================================================
// Centralized API Base and WebSocket configuration
// Automatically detects Local vs Cloud (Vercel/Render) environments
// ============================================================================

function sanitizeApiUrl(url) {
  if (!url || typeof url !== 'string') return null;
  const trimmed = url.trim();
  // Check if string contains masked password bullets or is not a valid URL
  if (trimmed.includes('•') || trimmed.includes('…') || (!trimmed.startsWith('http://') && !trimmed.startsWith('https://'))) {
    return null;
  }
  let corrected = trimmed.replace(/\/+$/, '');
  // Auto-correct /ap typo
  if (corrected.endsWith('/ap')) {
    corrected = corrected + 'i';
  }
  // Auto-correct old render service name if present
  if (corrected.includes('claimassist-4.onrender.com')) {
    corrected = corrected.replace('claimassist-4.onrender.com', 'claim-assist-2mvb.onrender.com');
  }
  return corrected;
}

const DEFAULT_PROD_API = 'https://claim-assist-2mvb.onrender.com/api';
const DEFAULT_DEV_API = 'http://127.0.0.1:8000/api';

const isLocalhost = typeof window !== 'undefined' && (
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1' ||
  window.location.hostname === '0.0.0.0' ||
  window.location.hostname === ''
);

// Clean and validate environment variable, falling back gracefully to reliable defaults
const validEnvUrl = sanitizeApiUrl(import.meta.env.VITE_API_BASE_URL);
const rawApiUrl = validEnvUrl || (isLocalhost ? DEFAULT_DEV_API : DEFAULT_PROD_API);

// Auto-derive WebSocket URL from API URL if VITE_WS_URL is not explicitly configured
function deriveWsUrl(apiUrl) {
  const customWs = sanitizeApiUrl(import.meta.env.VITE_WS_URL);
  if (customWs) {
    return customWs;
  }
  // Replace http/https with ws/wss and replace /api with /ws/live
  const wsProtocol = apiUrl.startsWith('https://') ? 'wss://' : 'ws://';
  const cleanHost = apiUrl.replace(/^https?:\/\//, '').replace(/\/api$/, '');
  return `${wsProtocol}${cleanHost}/ws/live`;
}

export const API_BASE_URL = rawApiUrl;
export const WS_URL = deriveWsUrl(rawApiUrl);

