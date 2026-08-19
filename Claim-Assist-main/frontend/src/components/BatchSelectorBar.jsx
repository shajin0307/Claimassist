import React, { useState, useEffect } from 'react';
import { getBatches, deleteBatch } from '../api';

export default function BatchSelectorBar({
  selectedBatchId,
  onSelectBatch,
  onOpenUpload,
  onOpenHistory,
  activeBatchInfo,
  totalRecords
}) {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadBatches();
  }, [selectedBatchId, activeBatchInfo]);

  const loadBatches = async () => {
    setLoading(true);
    const res = await getBatches();
    if (res.ok) {
      setBatches(res.data.batches || []);
    }
    setLoading(false);
  };

  const handleDropdownChange = (e) => {
    const val = e.target.value;
    onSelectBatch(val);
  };

  return (
    <div style={{
      background: 'linear-gradient(135deg, #ffffff 0%, #f8fafc 100%)',
      border: '1px solid var(--border-light)',
      borderRadius: 'var(--radius-lg)',
      padding: '12px 18px',
      marginBottom: 20,
      display: 'flex',
      flexWrap: 'wrap',
      justifyContent: 'space-between',
      alignItems: 'center',
      gap: 14,
      boxShadow: '0 1px 3px rgba(0,0,0,0.04)'
    }}>
      {/* Left side: Active Batch Information */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{
          width: 38,
          height: 38,
          borderRadius: 8,
          background: 'rgba(37, 99, 235, 0.1)',
          color: 'var(--primary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 18,
          fontWeight: 700
        }}>
          📊
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
              Active Analysis Scope
            </span>
            {activeBatchInfo && (
              <span className="badge" style={{ background: '#e0f2fe', color: '#0369a1', fontSize: 11, fontWeight: 600 }}>
                {activeBatchInfo.is_all ? 'All Uploads' : (selectedBatchId === 'latest' || !selectedBatchId ? 'Latest Upload' : 'Archived Batch')}
              </span>
            )}
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginTop: 1 }}>
            {activeBatchInfo?.filename || (totalRecords > 0 ? 'Live Ingestion Batch' : 'No CSV Uploaded Yet')}
            {activeBatchInfo?.uploaded_at && (
              <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--text-muted)', marginLeft: 8 }}>
                (Uploaded {new Date(activeBatchInfo.uploaded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Right side: Batch Selector Dropdown & Action Buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label htmlFor="batch-select" style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>
            Switch Analysis:
          </label>
          <select
            id="batch-select"
            value={selectedBatchId || 'latest'}
            onChange={handleDropdownChange}
            style={{
              padding: '6px 12px',
              fontSize: 13,
              fontWeight: 500,
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-medium)',
              background: '#fff',
              color: 'var(--text-primary)',
              cursor: 'pointer',
              outline: 'none',
              maxWidth: 240
            }}
          >
            <option value="latest">🌟 Latest Upload (Active)</option>
            {batches.map((b) => (
              <option key={b.batch_id} value={b.batch_id}>
                📁 {b.filename} ({b.total_records} rows • {new Date(b.uploaded_at).toLocaleDateString([], { month: 'short', day: 'numeric' })})
              </option>
            ))}
            {batches.length > 1 && (
              <option value="all">📊 All Uploads Combined</option>
            )}
          </select>
        </div>

        {batches.length > 0 && (
          <button
            className="btn btn--secondary btn--small"
            onClick={onOpenHistory}
            style={{ display: 'flex', alignItems: 'center', gap: 5 }}
          >
            <span>📜</span> Past Analyses ({batches.length})
          </button>
        )}

        <button
          className="btn btn--primary btn--small"
          onClick={onOpenUpload}
          style={{ display: 'flex', alignItems: 'center', gap: 5 }}
        >
          <span>⬆</span> Upload New File
        </button>
      </div>
    </div>
  );
}
