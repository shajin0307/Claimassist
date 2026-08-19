import React, { useState, useEffect, useCallback } from 'react';
import { getPredictions } from '../api';
import { SeverityBadge, PredictionBadge } from './OverviewDashboard';

export default function AnomaliesPage({ onSelectRecord, refreshTrigger, selectedBatchId }) {
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [predictionFilter, setPredictionFilter] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  const loadData = useCallback(async (p = page, prio = priorityFilter, pred = predictionFilter, bId = selectedBatchId) => {
    setLoading(true);
    setError(null);
    const res = await getPredictions(p, 20, prio !== 'ALL' ? prio : null, pred !== 'ALL' ? pred : null, bId);
    if (res.ok) {
      setPredictions(res.data.items || []);
      setTotal(res.data.total || 0);
      setTotalPages(res.data.total_pages || 1);
    } else {
      setError(res.error);
    }
    setLoading(false);
  }, [selectedBatchId]);

  useEffect(() => {
    loadData(1, priorityFilter, predictionFilter, selectedBatchId);
  }, [refreshTrigger, selectedBatchId]);

  const handlePriorityChange = (prio) => {
    setPriorityFilter(prio);
    setPage(1);
    loadData(1, prio, predictionFilter);
  };

  const handlePredictionChange = (pred) => {
    setPredictionFilter(pred);
    setPage(1);
    loadData(1, priorityFilter, pred);
  };

  const handlePageChange = (newPage) => {
    setPage(newPage);
    loadData(newPage, priorityFilter, predictionFilter);
  };

  // Client-side search filtering (on top of server-side filters)
  const filtered = searchTerm.trim()
    ? predictions.filter(p => {
        const term = searchTerm.toLowerCase();
        return (
          (p.auth_id && p.auth_id.toLowerCase().includes(term)) ||
          (p.prediction && p.prediction.toLowerCase().includes(term)) ||
          (p.final_priority && p.final_priority.toLowerCase().includes(term))
        );
      })
    : predictions;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 className="page-title">Anomalies</h2>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>
            {total > 0 ? `${total} authorization records` : 'Authorization records from backend'}
          </p>
        </div>
        <input
          type="text"
          className="search-input"
          placeholder="Search auth ID, prediction..."
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
        />
      </div>

      {/* Severity Filters */}
      <div className="filter-bar">
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginRight: 4 }}>Severity:</span>
        {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(f => (
          <button
            key={f}
            className={`filter-tab ${priorityFilter === f ? 'filter-tab--active' : ''}`}
            onClick={() => handlePriorityChange(f)}
          >
            {f === 'ALL' ? 'All' : f.charAt(0) + f.slice(1).toLowerCase()}
          </button>
        ))}

        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginLeft: 12, marginRight: 4 }}>Prediction:</span>
        {['ALL', 'ANOMALY', 'NORMAL'].map(f => (
          <button
            key={f}
            className={`filter-tab ${predictionFilter === f ? 'filter-tab--active' : ''}`}
            onClick={() => handlePredictionChange(f)}
          >
            {f === 'ALL' ? 'All' : f.charAt(0) + f.slice(1).toLowerCase()}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="card">
        {loading ? (
          <div className="loading-block">
            <div className="spinner" />
            <span>Loading authorization records...</span>
          </div>
        ) : error ? (
          <div className="error-block">
            <div className="error-block__icon">⚠</div>
            <div className="error-block__title">Unable to load anomaly data</div>
            <div className="error-block__message">{error}</div>
            <button className="btn btn--secondary btn--small" onClick={() => loadData(page, priorityFilter, predictionFilter)}>Retry</button>
          </div>
        ) : filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state__icon">✓</div>
            <div className="empty-state__title">No anomalies detected</div>
            <div className="empty-state__message">
              All processed records passed the configured validation and anomaly detection checks.
            </div>
          </div>
        ) : (
          <>
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Record / Auth ID</th>
                    <th>Severity</th>
                    <th>Prediction</th>
                    <th>Risk Score</th>
                    <th>SLA Risk</th>
                    <th>Rule Violations</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((item, idx) => (
                    <tr key={item.id || idx} onClick={() => onSelectRecord && onSelectRecord(item)}>
                      <td className="text-mono" style={{ fontWeight: 600 }}>{item.auth_id || `Record ${item.id}`}</td>
                      <td><SeverityBadge level={item.final_priority} /></td>
                      <td><PredictionBadge prediction={item.prediction} /></td>
                      <td style={{ fontWeight: 600 }}>{item.probability != null ? `${(item.probability * 100).toFixed(1)}%` : '—'}</td>
                      <td><SeverityBadge level={item.sla_risk} /></td>
                      <td>{item.rule_violations_count ?? 0}</td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        {item.timestamp ? formatTs(item.timestamp) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="pagination">
                <button
                  className="btn btn--ghost btn--small"
                  disabled={page <= 1}
                  onClick={() => handlePageChange(page - 1)}
                >
                  ← Previous
                </button>
                <span className="pagination__info">
                  Page {page} of {totalPages} ({total} records)
                </span>
                <button
                  className="btn btn--ghost btn--small"
                  disabled={page >= totalPages}
                  onClick={() => handlePageChange(page + 1)}
                >
                  Next →
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function formatTs(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return '—'; }
}
