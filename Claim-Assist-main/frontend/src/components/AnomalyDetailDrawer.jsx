import React, { useState, useEffect, useRef } from 'react';
import { SeverityBadge, PredictionBadge } from './OverviewDashboard';
import { startLLMExplanation, startGenericLLMExplanation, getLLMExplanation } from '../api';

export default function AnomalyDetailDrawer({ record, onClose }) {
  const [llmResult, setLlmResult] = useState(null);
  const [llmLoading, setLlmLoading] = useState(false);
  const [llmError, setLlmError] = useState(null);
  const [showEvidenceFeatures, setShowEvidenceFeatures] = useState(true);
  const pollTimerRef = useRef(null);
  const isCancelledRef = useRef(false);

  useEffect(() => {
    isCancelledRef.current = false;
    return () => {
      isCancelledRef.current = true;
      stopPolling();
    };
  }, []);

  if (!record) return null;

  const prio = record.final_priority || 'LOW';
  const pred = record.prediction || 'NORMAL';
  const prob = record.probability != null ? (record.probability * 100).toFixed(1) : '0.0';
  const reasons = record.reasons || [];

  const stopPolling = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  const pollExplanationStatus = (requestId) => {
    stopPolling();
    let attempts = 0;
    let consecutiveErrors = 0;
    const maxAttempts = 75; // 75 * 800ms = 60s

    pollTimerRef.current = setInterval(async () => {
      if (isCancelledRef.current) {
        stopPolling();
        return;
      }
      attempts += 1;

      const res = await getLLMExplanation(requestId);

      if (isCancelledRef.current) {
        stopPolling();
        return;
      }

      if (!res.ok) {
        consecutiveErrors += 1;
        if (consecutiveErrors >= 3 || attempts >= maxAttempts) {
          stopPolling();
          setLlmError(res.error || 'Failed to retrieve LLM explanation from backend.');
          setLlmLoading(false);
        }
        return;
      }

      consecutiveErrors = 0;
      const data = res.data;

      if (data.status === 'SUCCESS') {
        stopPolling();
        setLlmResult(data);
        setLlmError(null);
        setLlmLoading(false);
      } else if (data.status === 'LLM_UNAVAILABLE') {
        stopPolling();
        setLlmResult(data);
        setLlmError(null);
        setLlmLoading(false);
      } else if (data.status === 'ERROR') {
        stopPolling();
        setLlmError(data.message || 'LLM explanation generation failed.');
        setLlmLoading(false);
      } else if (attempts >= maxAttempts) {
        stopPolling();
        setLlmError('LLM explanation request timed out. Please retry.');
        setLlmLoading(false);
      }
    }, 800);
  };

  const handleGenerateLLM = async () => {
    stopPolling();
    setLlmLoading(true);
    setLlmError(null);
    setLlmResult(null);

    const authId = record.auth_id;
    let res = await startLLMExplanation(authId);

    // If the auth-specific endpoint fails (e.g. record not in DB), fallback to generic endpoint
    if (!res.ok) {
      const fallbackPayload = {
        issue_type: 'AUTHORIZATION_ANOMALY',
        reference_id: authId,
        evidence: {
          auth_id: authId,
          prediction: pred,
          probability: record.probability,
          threshold: 0.81,
          final_priority: prio,
          sla_risk: record.sla_risk,
          rule_violations_count: record.rule_violations_count,
          existing_reasons: reasons,
        },
      };
      res = await startGenericLLMExplanation(fallbackPayload);
    }

    if (!res.ok) {
      setLlmError(res.error || 'Failed to start LLM explanation.');
      setLlmLoading(false);
      return;
    }

    const data = res.data;
    if (data.status === 'PROCESSING' && data.request_id) {
      pollExplanationStatus(data.request_id);
    } else if (data.status === 'SUCCESS') {
      setLlmResult(data);
      setLlmLoading(false);
    } else if (data.status === 'LLM_UNAVAILABLE') {
      setLlmResult(data);
      setLlmLoading(false);
    } else {
      setLlmError(data.message || 'Unexpected response status.');
      setLlmLoading(false);
    }
  };

  const hasFeatureMetrics = (
    record.ml_req_units != null ||
    record.ml_aprvd_units != null ||
    record.ml_latency_hours != null ||
    record.ml_bene_age != null ||
    record.ml_prov_partd_cost != null
  );

  return (
    <div className="drawer-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="drawer-panel">
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20, paddingBottom: 16, borderBottom: '1px solid var(--border-light)' }}>
          <div>
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-muted)', marginBottom: 4 }}>
              Detailed Anomaly Analysis
            </div>
            <h2 style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
              {record.auth_id || 'Unknown'}
            </h2>
          </div>
          <button
            className="btn btn--ghost btn--icon-only"
            onClick={onClose}
            style={{ fontSize: 18, lineHeight: 1 }}
          >
            ✕
          </button>
        </div>

        {/* Primary Classification Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
          <DetailCell label="Final Priority" value={<SeverityBadge level={prio} />} />
          <DetailCell label="ML Prediction" value={<PredictionBadge prediction={pred} />} />
          <DetailCell label="Anomaly Probability" value={`${prob}%`} />
          <DetailCell label="Risk Rating" value={record.risk_level || prio} />
          <DetailCell label="SLA Urgency" value={<SeverityBadge level={record.sla_risk} />} />
          <DetailCell label="Policy Violations" value={`${record.rule_violations_count ?? 0} triggered`} />
          {record.timestamp && (
            <DetailCell label="Audit Timestamp" value={formatDetailTime(record.timestamp)} />
          )}
          {record.inference_latency_ms != null && (
            <DetailCell label="Inference Speed" value={`${record.inference_latency_ms.toFixed(2)} ms`} />
          )}
        </div>

        {/* Expandable Detection Evidence & Feature Values */}
        {hasFeatureMetrics && (
          <div style={{ marginBottom: 20 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                cursor: 'pointer',
                padding: '10px 14px',
                background: '#f8fafc',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-sm)',
                marginBottom: showEvidenceFeatures ? 8 : 0,
              }}
              onClick={() => setShowEvidenceFeatures(!showEvidenceFeatures)}
            >
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                Detection Evidence & Feature Values
              </span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {showEvidenceFeatures ? '▲ Hide' : '▼ Show'}
              </span>
            </div>

            {showEvidenceFeatures && (
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: 8,
                padding: 12,
                background: '#ffffff',
                border: '1px solid var(--border-light)',
                borderRadius: 'var(--radius-sm)',
              }}>
                {record.ml_req_units != null && (
                  <FeatureItem label="Requested Units" value={record.ml_req_units} />
                )}
                {record.ml_aprvd_units != null && (
                  <FeatureItem label="Approved Units" value={record.ml_aprvd_units} />
                )}
                {record.ml_latency_hours != null && (
                  <FeatureItem label="Processing Latency" value={`${record.ml_latency_hours} hrs`} />
                )}
                {record.ml_bene_age != null && (
                  <FeatureItem label="Beneficiary Age" value={`${Math.round(record.ml_bene_age)} yrs`} />
                )}
                {record.ml_prov_partd_cost != null && (
                  <FeatureItem label="Provider Part D Cost" value={`$${Number(record.ml_prov_partd_cost).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} />
                )}
                {record.rule_violations_count != null && (
                  <FeatureItem label="Rule Violations" value={record.rule_violations_count} />
                )}
              </div>
            )}
          </div>
        )}

        {/* Evidence / Reasons Section */}
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
            Detection Reasons & Triggers
          </h3>
          {reasons.length === 0 ? (
            <div style={{
              padding: 12, borderRadius: 'var(--radius-sm)',
              background: 'var(--success-bg)', color: 'var(--success)',
              fontSize: 13, fontWeight: 500,
            }}>
              ✓ All deterministic policy rules, SLA timeframes, and ML metrics evaluated within normal baseline.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {reasons.map((reason, idx) => (
                <div key={idx} style={{
                  padding: '9px 12px', borderRadius: 'var(--radius-sm)',
                  background: '#f8fafc', border: '1px solid var(--border-light)',
                  fontSize: 12.5, color: 'var(--text-secondary)',
                  display: 'flex', alignItems: 'flex-start', gap: 8,
                }}>
                  <span style={{ color: 'var(--warning)', flexShrink: 0 }}>⚠</span>
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recommended Action */}
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
            Recommended Operational Action
          </h3>
          <div style={{
            padding: 12,
            background: '#f8fafc',
            border: '1px solid var(--border-light)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 13,
            color: 'var(--text-secondary)',
            lineHeight: 1.5,
          }}>
            {getRecommendedAction(record)}
          </div>
        </div>

        {/* Evidence-Grounded AI Explanation Section */}
        <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div>
              <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--accent-blue)', margin: 0 }}>
                AI Explanation (Llama 3.2)
              </h3>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                Evidence-grounded causal analysis from backend LLM
              </div>
            </div>
            <button
              className="btn btn--primary btn--small"
              onClick={handleGenerateLLM}
              disabled={llmLoading}
            >
              {llmLoading ? (
                <><div className="spinner spinner--sm" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} /> Generating...</>
              ) : (
                'Generate AI Explanation'
              )}
            </button>
          </div>

          {llmLoading && (
            <div style={{
              padding: 16, background: 'var(--info-bg)', borderRadius: 'var(--radius-sm)',
              color: 'var(--info)', fontSize: 13, display: 'flex', alignItems: 'center', gap: 10,
            }}>
              <div className="spinner spinner--sm" style={{ borderTopColor: 'var(--info)' }} />
              Generating evidence-grounded explanation...
            </div>
          )}

          {llmError && (
            <div style={{
              padding: 14, background: 'var(--critical-bg)', border: '1px solid var(--critical-border)',
              borderRadius: 'var(--radius-sm)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span style={{ color: 'var(--critical)', fontSize: 13 }}>
                AI explanation unavailable. {llmError}
              </span>
              <button className="btn btn--danger btn--small" onClick={handleGenerateLLM}>Retry</button>
            </div>
          )}

          {llmResult && llmResult.status === 'LLM_UNAVAILABLE' && !llmError && (
            <div style={{
              padding: 14, background: 'var(--warning-bg)', border: '1px solid var(--warning-border)',
              borderRadius: 'var(--radius-sm)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}>
              <span style={{ color: 'var(--warning)', fontSize: 13 }}>
                AI explanation unavailable. {llmResult.message || 'Ollama connection timeout.'}
              </span>
              <button className="btn btn--secondary btn--small" onClick={handleGenerateLLM}>Retry</button>
            </div>
          )}

          {llmResult && llmResult.status === 'SUCCESS' && (
            <div className="llm-result">
              <div className="llm-result__header">
                <span className="llm-result__label">Evidence-Grounded AI Analysis</span>
                <span className="llm-result__confidence">
                  Confidence: {((llmResult.confidence || 0) * 100).toFixed(0)}%
                </span>
              </div>

              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 14, fontStyle: 'italic' }}>
                Explanations synthesize deterministic evidence without altering core ML predictions or business rules.
              </div>

              {llmResult.likely_cause && (
                <div className="llm-result__section">
                  <div className="llm-result__section-title">Likely Cause</div>
                  <div className="llm-result__section-body">{llmResult.likely_cause}</div>
                </div>
              )}

              {llmResult.business_impact && (
                <div className="llm-result__section">
                  <div className="llm-result__section-title">Business Impact</div>
                  <div className="llm-result__section-body">{llmResult.business_impact}</div>
                </div>
              )}

              {llmResult.recommended_fix && (
                <div className="llm-result__section">
                  <div className="llm-result__section-title">Recommended Fix</div>
                  <div className="llm-result__section-body">{llmResult.recommended_fix}</div>
                </div>
              )}

              {llmResult.evidence_used?.length > 0 && (
                <div className="llm-result__section">
                  <div className="llm-result__section-title">Evidence Used</div>
                  <ul className="llm-result__evidence-list">
                    {llmResult.evidence_used.map((ev, i) => (
                      <li key={i}>{ev}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div style={{ display: 'flex', gap: 16, marginTop: 12, paddingTop: 10, borderTop: '1px solid #e2e8f0', fontSize: 11, color: 'var(--text-muted)' }}>
                <span>Provider: <strong>{llmResult.provider || 'ollama'}</strong></span>
                <span>Model: <strong>{llmResult.model || 'llama3.2:3b'}</strong></span>
                {llmResult.latency_ms != null && <span>Latency: <strong>{(llmResult.latency_ms / 1000).toFixed(2)}s</strong></span>}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: 20, marginTop: 20, borderTop: '1px solid var(--border-light)' }}>
          <button className="btn btn--secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components & Helpers
// ---------------------------------------------------------------------------

function DetailCell({ label, value }) {
  return (
    <div style={{
      padding: 12, borderRadius: 'var(--radius-sm)',
      background: '#f8fafc', border: '1px solid var(--border-light)',
    }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
        {label}
      </div>
      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
        {value}
      </div>
    </div>
  );
}

function FeatureItem({ label, value }) {
  return (
    <div style={{ padding: '6px 8px', background: '#f8fafc', borderRadius: 4 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{label}</div>
      <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)', marginTop: 1 }}>
        {value}
      </div>
    </div>
  );
}

function getRecommendedAction(record) {
  const prio = record.final_priority || 'LOW';
  if (prio === 'CRITICAL') return 'Immediately escalate to clinical review and compliance queue. Validate source authorization units and provider authorization history before approval.';
  if (prio === 'HIGH') return 'Prioritize for supervisor audit. Verify unit ratios against medical policy and review prior authorization records.';
  if (prio === 'MEDIUM') return 'Routine queue verification. Cross-check service line count with standard clinical policy guidelines.';
  return 'Standard automated processing. All parameters conform to expected baseline thresholds.';
}

function formatDetailTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-US', {
      month: 'short', day: 'numeric', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch { return '—'; }
}
