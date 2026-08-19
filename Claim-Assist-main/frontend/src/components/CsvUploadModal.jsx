import React, { useState } from 'react';
import { uploadCSV } from '../api';
import { SeverityBadge, PredictionBadge } from './OverviewDashboard';

const BASE_FEATURES = [
  'ml_req_units',
  'ml_aprvd_units',
  'ml_units_diff',
  'ml_units_ratio',
  'ml_latency_hours',
  'ml_bene_carrier_cnt',
  'ml_bene_outpatient_cnt',
  'ml_bene_pde_cnt',
  'ml_bene_total_utilization',
  'ml_bene_gender',
  'ml_bene_race',
  'ml_bene_age',
  'ml_prov_partd_clms',
  'ml_prov_partd_cost',
  'ml_prov_avg_cost_per_clm',
  'has_partd_provider_match',
];

export default function CsvUploadModal({ onClose, onBatchSuccess }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [batchResult, setBatchResult] = useState(null);
  const [showContractInfo, setShowContractInfo] = useState(false);

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a CSV file to upload.');
      return;
    }
    setLoading(true);
    setError(null);

    const res = await uploadCSV(file);
    if (res.ok) {
      setBatchResult(res.data);
      if (onBatchSuccess) onBatchSuccess(res.data);
    } else {
      setError(res.error || 'Failed to process CSV file.');
    }
    setLoading(false);
  };

  const summary = batchResult?.summary;
  const results = batchResult?.results || [];
  const priorityDist = summary?.priority_distribution || {};

  // Check if all records were classified as anomaly (often indicates generic non-ml CSV schema)
  const isHighAnomalyBatch = summary?.total_records > 0 && summary?.anomaly_rate === 1.0;

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-panel" style={{ maxWidth: batchResult ? 780 : 600 }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border-light)' }}>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
              {batchResult ? 'Batch Analysis Results' : 'Upload Authorization CSV'}
            </h2>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              Processed directly through the backend 25-feature ML anomaly pipeline
            </p>
          </div>
          <button className="btn btn--ghost btn--icon-only" onClick={onClose} style={{ fontSize: 18 }}>✕</button>
        </div>

        {!batchResult ? (
          <div>
            {/* Model Contract Collapsible Panel */}
            <div style={{ marginBottom: 16, border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
              <div
                style={{
                  padding: '10px 14px',
                  background: '#f8fafc',
                  cursor: 'pointer',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontSize: 12.5,
                  fontWeight: 600,
                  color: 'var(--text-secondary)',
                }}
                onClick={() => setShowContractInfo(!showContractInfo)}
              >
                <span>ℹ Model Contract & Input Format Information</span>
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {showContractInfo ? '▲ Hide schema' : '▼ View 16 base fields'}
                </span>
              </div>

              {showContractInfo && (
                <div style={{ padding: '12px 14px', background: '#ffffff', fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                  <p style={{ marginBottom: 8 }}>
                    This anomaly model expects the backend's established ML feature schema. Generic claim columns may be accepted by the upload endpoint but will be converted to configured fallback values by backend feature engineering.
                  </p>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                    16 Base Model Features:
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 4, fontFamily: 'monospace', fontSize: 11, color: 'var(--accent-blue)' }}>
                    {BASE_FEATURES.map((feat) => (
                      <div key={feat}>• {feat}</div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Drop Zone */}
            <div style={{
              padding: 32,
              border: '2px dashed var(--border-medium)',
              borderRadius: 'var(--radius-lg)',
              textAlign: 'center',
              background: '#fafbfc',
              marginBottom: 16,
            }}>
              <div style={{ fontSize: 32, marginBottom: 8, opacity: 0.5 }}>📄</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>
                Select a CSV file to upload
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
                Claims & authorization batches are evaluated against trained Autoencoder & Logistic Regression
              </div>

              <input
                type="file"
                accept=".csv"
                id="csv-upload-input"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
              <label
                htmlFor="csv-upload-input"
                className="btn btn--secondary"
                style={{ cursor: 'pointer', display: 'inline-flex' }}
              >
                Choose CSV File
              </label>

              {file && (
                <div style={{ marginTop: 12, fontSize: 13, color: 'var(--accent-blue)', fontWeight: 600 }}>
                  Selected: {file.name} ({(file.size / 1024).toFixed(1)} KB)
                </div>
              )}
            </div>

            {error && (
              <div style={{
                padding: 12, borderRadius: 'var(--radius-sm)',
                background: 'var(--critical-bg)', border: '1px solid var(--critical-border)',
                color: 'var(--critical)', fontSize: 13, marginBottom: 16,
              }}>
                {error}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button className="btn btn--ghost" onClick={onClose}>Cancel</button>
              <button
                className="btn btn--primary"
                onClick={handleUpload}
                disabled={loading || !file}
              >
                {loading ? (
                  <><div className="spinner spinner--sm" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} /> Processing CSV...</>
                ) : (
                  'Upload & Process'
                )}
              </button>
            </div>
          </div>
        ) : (
          <div>
            {/* Success Banner */}
            <div style={{
              padding: '12px 16px', borderRadius: 'var(--radius-md)',
              background: 'var(--success-bg)', border: '1px solid var(--success-border)',
              color: 'var(--success)', fontSize: 13.5, fontWeight: 600, marginBottom: 16,
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              ✓ Batch processed successfully ({summary.total_records} records evaluated)
            </div>

            {/* Informational Banner for Fallback Schema */}
            {isHighAnomalyBatch && (
              <div style={{
                padding: '10px 14px', borderRadius: 'var(--radius-md)',
                background: '#fffbeb', border: '1px solid #fef3c7',
                color: '#92400e', fontSize: 12, marginBottom: 16, lineHeight: 1.5,
              }}>
                <strong>Notice:</strong> Model-compatible feature fields were not supplied. The backend feature engineering pipeline used its configured fallback values, which can produce out-of-distribution inputs and extreme anomaly probabilities.
              </div>
            )}

            {/* Metrics Summary Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 14 }}>
              <ResultCard label="Total Records" value={summary.total_records} />
              <ResultCard label="Normal" value={summary.normal_count} />
              <ResultCard label="Anomalies" value={summary.anomaly_count} highlight={summary.anomaly_count > 0} />
              <ResultCard label="Anomaly Rate" value={`${(summary.anomaly_rate * 100).toFixed(1)}%`} />
            </div>

            {/* Priority Distribution & Latency */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 14 }}>
              <ResultCard label="Low Priority" value={priorityDist.LOW || 0} />
              <ResultCard label="Medium Priority" value={priorityDist.MEDIUM || 0} />
              <ResultCard label="High Priority" value={priorityDist.HIGH || 0} />
              <ResultCard label="Critical Priority" value={priorityDist.CRITICAL || 0} highlight={(priorityDist.CRITICAL || 0) > 0} />
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: '#f8fafc', borderRadius: 'var(--radius-sm)', marginBottom: 16, fontSize: 12, color: 'var(--text-secondary)' }}>
              <span>Avg Latency: <strong>{summary.avg_inference_latency_ms} ms</strong></span>
              <span>Data Quality: <em>Not provided by batch prediction endpoint</em></span>
            </div>

            {/* Individual Records Table */}
            <div style={{ maxHeight: 240, overflowY: 'auto', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)', marginBottom: 16 }}>
              <table className="data-table" style={{ fontSize: 12 }}>
                <thead>
                  <tr>
                    <th>Auth ID</th>
                    <th>Prediction</th>
                    <th>Risk / Prob</th>
                    <th>SLA Risk</th>
                    <th>Rules</th>
                    <th>Priority</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, idx) => (
                    <tr key={r.auth_id || idx}>
                      <td className="text-mono" style={{ fontWeight: 600 }}>{r.auth_id}</td>
                      <td><PredictionBadge prediction={r.prediction} /></td>
                      <td style={{ fontWeight: 600 }}>{(r.probability * 100).toFixed(1)}%</td>
                      <td><SeverityBadge level={r.sla_risk} /></td>
                      <td>{r.rule_violations_count ?? 0}</td>
                      <td><SeverityBadge level={r.final_priority} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <button className="btn btn--secondary btn--small" onClick={() => { setBatchResult(null); setFile(null); }}>
                Upload Another File
              </button>
              <button className="btn btn--primary" onClick={onClose}>
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ResultCard({ label, value, highlight }) {
  return (
    <div style={{
      padding: '10px 8px', borderRadius: 'var(--radius-sm)',
      background: '#f8fafc', border: '1px solid var(--border-light)',
      textAlign: 'center',
    }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{label}</div>
      <div style={{
        fontSize: 18, fontWeight: 800,
        color: highlight ? 'var(--critical)' : 'var(--text-primary)',
      }}>{value}</div>
    </div>
  );
}
