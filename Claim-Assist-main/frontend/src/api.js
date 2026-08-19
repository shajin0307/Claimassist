// ============================================================================
// ClaimGuard AI — Centralized API Service Layer
// Every backend request flows through this module.
// Components must NOT contain raw fetch() calls.
// ============================================================================

import { API_BASE_URL } from './config';

// ---------------------------------------------------------------------------
// Core request helper with timeout, status validation, and error handling
// ---------------------------------------------------------------------------

export async function fetchWithTimeout(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const mergedOptions = {
    ...options,
    signal: controller.signal,
  };

  try {
    const response = await fetch(url, mergedOptions);
    clearTimeout(timeoutId);
    return response;
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === 'AbortError') {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    }
    throw err;
  }
}

/**
 * Standard JSON request helper.
 * Returns { ok: true, data } on success, { ok: false, error } on failure.
 */
async function apiRequest(path, options = {}, timeoutMs = 15000) {
  const url = `${API_BASE_URL}${path}`;
  try {
    const res = await fetchWithTimeout(url, options, timeoutMs);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const errBody = await res.json();
        detail = errBody.detail || detail;
      } catch (_) { /* ignore parse error */ }
      return { ok: false, error: detail };
    }
    const data = await res.json();
    return { ok: true, data };
  } catch (err) {
    return { ok: false, error: err.message || 'Network request failed' };
  }
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export async function getHealth() {
  return apiRequest('/health');
}

// ---------------------------------------------------------------------------
// Batches (Upload sessions & analysis isolation)
// ---------------------------------------------------------------------------

export async function getBatches() {
  return apiRequest('/batches', {}, 10000);
}

export async function getLatestBatch() {
  return apiRequest('/batches/latest', {}, 10000);
}

export async function deleteBatch(batchId) {
  return apiRequest(`/batches/${encodeURIComponent(batchId)}`, {
    method: 'DELETE',
  }, 10000);
}

// ---------------------------------------------------------------------------
// Statistics (dashboard KPIs, scoped by batch)
// ---------------------------------------------------------------------------

export async function getStats(batchId = null) {
  let path = '/stats';
  if (batchId) {
    path += `?batch_id=${encodeURIComponent(batchId)}`;
  }
  return apiRequest(path, {}, 10000);
}

// ---------------------------------------------------------------------------
// Predictions / Authorizations
// ---------------------------------------------------------------------------

export async function getPredictions(page = 1, pageSize = 20, priority = null, prediction = null, batchId = null) {
  let path = `/predictions?page=${page}&page_size=${pageSize}`;
  if (priority && priority !== 'ALL') path += `&priority=${encodeURIComponent(priority)}`;
  if (prediction && prediction !== 'ALL') path += `&prediction=${encodeURIComponent(prediction)}`;
  if (batchId) path += `&batch_id=${encodeURIComponent(batchId)}`;
  return apiRequest(path, {}, 10000);
}

// ---------------------------------------------------------------------------
// Data Quality Report (cached backend engine)
// ---------------------------------------------------------------------------

export async function getDataQualityReport(maxChunks = 1, forceRefresh = false) {
  let path = `/data-quality/report?max_chunks=${maxChunks}`;
  if (forceRefresh) path += '&force_refresh=true';
  return apiRequest(path, {}, 30000);
}

// ---------------------------------------------------------------------------
// Freshness Report (cached backend engine)
// ---------------------------------------------------------------------------

export async function getFreshnessReport(maxChunks = 1, forceRefresh = false) {
  let path = `/freshness/report?max_chunks=${maxChunks}`;
  if (forceRefresh) path += '&force_refresh=true';
  return apiRequest(path, {}, 30000);
}

// ---------------------------------------------------------------------------
// Cross-Domain Consistency Report (cached backend engine)
// ---------------------------------------------------------------------------

export async function getCrossDomainReport(forceRefresh = false) {
  let path = '/cross-domain/report';
  if (forceRefresh) path += '?force_refresh=true';
  return apiRequest(path, {}, 30000);
}

// ---------------------------------------------------------------------------
// Care Management Signals (cached backend engine)
// ---------------------------------------------------------------------------

export async function getCareSignals(forceRefresh = false) {
  let path = '/care-management/signals';
  if (forceRefresh) path += '?force_refresh=true';
  return apiRequest(path, {}, 30000);
}

// ---------------------------------------------------------------------------
// Decision Impact Report (cached backend engine)
// ---------------------------------------------------------------------------

export async function getDecisionImpact(forceRefresh = false) {
  let path = '/decision-impact/report';
  if (forceRefresh) path += '?force_refresh=true';
  return apiRequest(path, {}, 30000);
}

// ---------------------------------------------------------------------------
// CSV Upload — batch predict
// ---------------------------------------------------------------------------

export async function uploadCSV(file) {
  const formData = new FormData();
  formData.append('file', file);

  return apiRequest('/batch-predict', {
    method: 'POST',
    body: formData,
  }, 180000);
}

// ---------------------------------------------------------------------------
// Simulate Authorization Event
// ---------------------------------------------------------------------------

export async function simulateAuthorization() {
  return apiRequest('/stream/simulate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  }, 15000);
}

// ---------------------------------------------------------------------------
// LLM Explanation — start for authorization record
// ---------------------------------------------------------------------------

export async function startLLMExplanation(authId) {
  return apiRequest(`/llm/explain/authorization/${encodeURIComponent(authId)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  }, 15000);
}

// ---------------------------------------------------------------------------
// LLM Explanation — generic (fallback when record not in DB)
// ---------------------------------------------------------------------------

export async function startGenericLLMExplanation(payload) {
  return apiRequest('/llm/explain', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }, 15000);
}

// ---------------------------------------------------------------------------
// LLM Explanation — poll status
// ---------------------------------------------------------------------------

export async function getLLMExplanation(requestId) {
  return apiRequest(`/llm/explanation/${encodeURIComponent(requestId)}`, {}, 5000);
}
