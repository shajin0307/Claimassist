import React, { useState, useEffect } from 'react';
import { getBatches, deleteBatch } from '../api';

export default function BatchHistoryModal({
  isOpen,
  onClose,
  currentBatchId,
  onSelectBatch
}) {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);

  useEffect(() => {
    if (isOpen) {
      loadBatches();
    }
  }, [isOpen]);

  const loadBatches = async () => {
    setLoading(true);
    const res = await getBatches();
    if (res.ok) {
      setBatches(res.data.batches || []);
    }
    setLoading(false);
  };

  const handleDelete = async (batchId, e) => {
    e.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this batch and its analysis records?')) {
      return;
    }
    setDeletingId(batchId);
    const res = await deleteBatch(batchId);
    if (res.ok) {
      setBatches(prev => prev.filter(b => b.batch_id !== batchId));
      if (currentBatchId === batchId) {
        onSelectBatch('latest');
      }
    }
    setDeletingId(null);
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal-panel" style={{ maxWidth: 850, maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, paddingBottom: 12, borderBottom: '1px solid var(--border-light)' }}>
          <div>
            <h2 style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
              📜 Uploaded Analyses History
            </h2>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              Every CSV file upload is stored as an independent analysis session. Select any batch to inspect its results.
            </p>
          </div>
          <button className="btn btn--ghost btn--icon-only" onClick={onClose} style={{ fontSize: 18 }}>✕</button>
        </div>

        {/* Content */}
        <div style={{ overflowY: 'auto', flex: 1, paddingRight: 4 }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
              Loading analysis history...
            </div>
          ) : batches.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>📁</div>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>No Past Uploads Found</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                Upload a CSV file using the "Upload CSV" button to create an isolated analysis session.
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {batches.map((b, idx) => {
                const isSelected = (currentBatchId === b.batch_id) || (idx === 0 && (currentBatchId === 'latest' || !currentBatchId));
                const anomalyPct = (b.anomaly_rate * 100).toFixed(1);

                return (
                  <div
                    key={b.batch_id}
                    className="card"
                    style={{
                      padding: 16,
                      border: isSelected ? '2px solid var(--primary)' : '1px solid var(--border-light)',
                      background: isSelected ? 'rgba(37, 99, 235, 0.02)' : '#fff',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease'
                    }}
                    onClick={() => {
                      onSelectBatch(b.batch_id);
                      onClose();
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{
                          width: 36,
                          height: 36,
                          borderRadius: 6,
                          background: isSelected ? 'var(--primary)' : '#f1f5f9',
                          color: isSelected ? '#fff' : 'var(--text-secondary)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 700,
                          fontSize: 14
                        }}>
                          #{batches.length - idx}
                        </div>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>
                              {b.filename}
                            </span>
                            {idx === 0 && (
                              <span className="badge badge--info" style={{ fontSize: 10 }}>Latest</span>
                            )}
                            {isSelected && (
                              <span className="badge badge--success" style={{ fontSize: 10 }}>Active Scope</span>
                            )}
                          </div>
                          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                            Uploaded on {new Date(b.uploaded_at).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })} at {new Date(b.uploaded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </div>
                        </div>
                      </div>

                      {/* Right Stats & Action */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>
                            {b.total_records} Total Claims
                          </div>
                          <div style={{ fontSize: 11, color: b.anomaly_count > 0 ? 'var(--critical)' : 'var(--success)', marginTop: 1 }}>
                            {b.anomaly_count} Anomalies ({anomalyPct}%)
                          </div>
                        </div>

                        <div style={{ display: 'flex', gap: 6 }}>
                          <button
                            className={`btn btn--small ${isSelected ? 'btn--primary' : 'btn--secondary'}`}
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectBatch(b.batch_id);
                              onClose();
                            }}
                          >
                            {isSelected ? '✓ Viewing' : 'View Analysis'}
                          </button>
                          <button
                            className="btn btn--danger btn--small"
                            onClick={(e) => handleDelete(b.batch_id, e)}
                            disabled={deletingId === b.batch_id}
                            title="Delete this batch and its records"
                          >
                            {deletingId === b.batch_id ? '...' : '🗑'}
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Priority breakdown mini-bar */}
                    <div style={{ display: 'flex', gap: 12, marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--border-light)', fontSize: 11, color: 'var(--text-secondary)' }}>
                      <span>Normal: <b style={{ color: 'var(--success)' }}>{b.normal_count}</b></span>
                      <span>Low: <b>{b.priority_distribution?.LOW || 0}</b></span>
                      <span>Medium: <b>{b.priority_distribution?.MEDIUM || 0}</b></span>
                      <span>High: <b style={{ color: 'var(--warning)' }}>{b.priority_distribution?.HIGH || 0}</b></span>
                      <span>Critical: <b style={{ color: 'var(--critical)' }}>{b.priority_distribution?.CRITICAL || 0}</b></span>
                      {b.avg_inference_latency_ms > 0 && (
                        <span style={{ marginLeft: 'auto', color: 'var(--text-muted)' }}>
                          Latency: {b.avg_inference_latency_ms}ms/claim
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border-light)' }}>
          <button
            className="btn btn--ghost btn--small"
            onClick={() => {
              onSelectBatch('all');
              onClose();
            }}
          >
            📊 View All Uploads Combined
          </button>
          <button className="btn btn--secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
