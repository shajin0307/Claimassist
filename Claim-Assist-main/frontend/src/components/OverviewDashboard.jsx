import React, { useState, useEffect } from 'react';
import { getStats, getDataQualityReport, getPredictions } from '../api';

export default function OverviewDashboard({ stats, dataQuality, lastRefreshed, onNavigate }) {
  const [predictions, setPredictions] = useState([]);
  const [predsLoading, setPredsLoading] = useState(true);
  const [predsError, setPredsError] = useState(null);

  useEffect(() => {
    loadRecentAnomalies();
  }, [stats]);

  const loadRecentAnomalies = async () => {
    setPredsLoading(true);
    setPredsError(null);
    const res = await getPredictions(1, 10);
    if (res.ok) {
      setPredictions(res.data.items || []);
    } else {
      setPredsError(res.error);
    }
    setPredsLoading(false);
  };

  // KPI values from backend stats
  const totalRecords = stats?.total_requests || 0;
  const anomalyCount = stats?.anomaly_count || 0;
  const normalCount = stats?.normal_count || 0;
  const anomalyRate = stats?.anomaly_rate != null ? (stats.anomaly_rate * 100).toFixed(1) : (totalRecords > 0 ? ((anomalyCount / totalRecords) * 100).toFixed(1) : '0.0');
  
  const priorityDist = stats?.priority_distribution || {};
  const criticalCount = priorityDist.CRITICAL || 0;
  const highCount = priorityDist.HIGH || 0;
  const mediumCount = priorityDist.MEDIUM || 0;
  const lowCount = priorityDist.LOW || 0;

  // Quality score from data quality report
  const qualityScore = dataQuality?.summary?.overall_cms_quality_score ?? null;

  // Breakdown for Donut Chart
  const warningCount = mediumCount + highCount;
  const errorCount = criticalCount;
  const validCount = normalCount;

  // Anomaly categories from predictions
  const anomaliesByType = computeAnomalyCategories(predictions);

  // Donut chart percentages
  const donutTotal = totalRecords || 1;
  const validPct = Math.min(100, (Math.max(0, validCount) / donutTotal) * 100);
  const warnPct = Math.min(100, (warningCount / donutTotal) * 100);
  const errPct = Math.min(100, (errorCount / donutTotal) * 100);

  return (
    <div>
      {/* 5 Primary KPI Cards */}
      <div className="kpi-grid">
        {/* Card 1 — Quality */}
        <div className="kpi-card">
          <div className="kpi-card__label">Data Quality Score</div>
          <div className="kpi-card__value" style={{ color: qualityScore !== null && qualityScore >= 80 ? 'var(--success)' : qualityScore !== null && qualityScore >= 50 ? 'var(--warning)' : 'var(--text-primary)' }}>
            {qualityScore !== null ? `${qualityScore.toFixed(1)}%` : '—'}
          </div>
          <div className={`kpi-card__sub ${qualityScore !== null && qualityScore >= 80 ? 'kpi-card__sub--good' : qualityScore !== null && qualityScore < 50 ? 'kpi-card__sub--critical' : ''}`}>
            {qualityScore !== null ? (qualityScore >= 90 ? 'CMS Rules Passed' : qualityScore >= 80 ? 'Good' : 'Needs Review') : 'Validating CMS data...'}
          </div>
        </div>

        {/* Card 2 — Total Records */}
        <div className="kpi-card">
          <div className="kpi-card__label">Total Records</div>
          <div className="kpi-card__value">{totalRecords.toLocaleString()}</div>
          <div className="kpi-card__sub">{normalCount.toLocaleString()} normal ({totalRecords > 0 ? ((normalCount / totalRecords) * 100).toFixed(1) : 0}%)</div>
        </div>

        {/* Card 3 — Anomalies Detected */}
        <div className="kpi-card">
          <div className="kpi-card__label">Anomalies Detected</div>
          <div className="kpi-card__value" style={{ color: anomalyCount > 0 ? 'var(--critical)' : 'var(--success)' }}>
            {anomalyCount.toLocaleString()}
          </div>
          <div className={`kpi-card__sub ${anomalyCount > 0 ? 'kpi-card__sub--critical' : 'kpi-card__sub--good'}`}>
            {anomalyRate}% anomaly rate
          </div>
        </div>

        {/* Card 4 — Critical Issues */}
        <div className="kpi-card">
          <div className="kpi-card__label">Critical Issues</div>
          <div className="kpi-card__value" style={{ color: criticalCount > 0 ? 'var(--critical)' : 'var(--success)' }}>
            {criticalCount.toLocaleString()}
          </div>
          <div className={`kpi-card__sub ${criticalCount > 0 ? 'kpi-card__sub--critical' : 'kpi-card__sub--good'}`}>
            {criticalCount > 0 ? `${criticalCount} urgent reviews` : 'Zero critical issues'}
          </div>
        </div>

        {/* Card 5 — Priority Breakdown */}
        <div className="kpi-card">
          <div className="kpi-card__label">Priority Overview</div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4, marginBottom: 4 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--critical)' }}>Crit: {criticalCount}</span>
            <span style={{ color: 'var(--border-medium)' }}>|</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--warning)' }}>High: {highCount}</span>
            <span style={{ color: 'var(--border-medium)' }}>|</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--medium-color)' }}>Med: {mediumCount}</span>
          </div>
          <div className="kpi-card__sub" style={{ marginTop: 2 }}>
            {lastRefreshed ? `Refreshed ${formatTime(lastRefreshed)}` : 'Live synchronized'}
          </div>
        </div>
      </div>

      {/* Two-column: Data Quality Overview + Anomalies by Type */}
      <div className="two-col">
        {/* Data Quality Overview */}
        <div className="card">
          <div className="card__header">
            <div>
              <div className="card__title">Dataset Quality & Health Breakdown</div>
              <div className="card__subtitle">Aggregated from backend rules & ML inference</div>
            </div>
          </div>

          {/* Donut Chart */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 32, flexWrap: 'wrap' }}>
            <div className="donut-chart">
              <svg viewBox="0 0 36 36" width="180" height="180">
                <circle cx="18" cy="18" r="14" fill="none" stroke="#f1f5f9" strokeWidth="4" />
                <circle cx="18" cy="18" r="14" fill="none" stroke="#16a34a" strokeWidth="4"
                  strokeDasharray={`${validPct * 0.88} ${88 - validPct * 0.88}`}
                  strokeDashoffset="25" strokeLinecap="round" />
                <circle cx="18" cy="18" r="14" fill="none" stroke="#ea580c" strokeWidth="4"
                  strokeDasharray={`${warnPct * 0.88} ${88 - warnPct * 0.88}`}
                  strokeDashoffset={`${25 - validPct * 0.88}`} strokeLinecap="round" />
                <circle cx="18" cy="18" r="14" fill="none" stroke="#dc2626" strokeWidth="4"
                  strokeDasharray={`${errPct * 0.88} ${88 - errPct * 0.88}`}
                  strokeDashoffset={`${25 - (validPct + warnPct) * 0.88}`} strokeLinecap="round" />
              </svg>
              <div className="donut-chart__center">
                <div className="donut-chart__center-value">{totalRecords.toLocaleString()}</div>
                <div className="donut-chart__center-label">Evaluated</div>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, flex: 1, minWidth: 160 }}>
              <LegendRow color="#16a34a" label="Normal / Low Risk" value={Math.max(0, validCount)} />
              <LegendRow color="#2563eb" label="Medium Priority" value={mediumCount} />
              <LegendRow color="#ea580c" label="High Priority" value={highCount} />
              <LegendRow color="#dc2626" label="Critical Priority" value={criticalCount} />
            </div>
          </div>
        </div>

        {/* Anomalies by Type */}
        <div className="card">
          <div className="card__header">
            <div>
              <div className="card__title">Anomaly Distribution by Category</div>
              <div className="card__subtitle">Derived from active detection triggers</div>
            </div>
            <button className="btn btn--ghost btn--small" onClick={() => onNavigate('ANOMALIES')}>
              View All →
            </button>
          </div>

          {anomaliesByType.length === 0 ? (
            <div className="empty-state" style={{ padding: '32px 16px' }}>
              <div className="empty-state__icon">✓</div>
              <div className="empty-state__title">No anomalies detected</div>
              <div className="empty-state__message">All processed records are currently within normal baseline thresholds.</div>
            </div>
          ) : (
            <div className="h-bar">
              {anomaliesByType.map((item) => (
                <div className="h-bar__row" key={item.label}>
                  <div className="h-bar__label">{item.label}</div>
                  <div className="h-bar__track">
                    <div className="h-bar__fill" style={{
                      width: `${Math.max(5, (item.count / Math.max(1, anomaliesByType[0]?.count || 1)) * 100)}%`,
                      background: item.color
                    }} />
                  </div>
                  <div className="h-bar__count">{item.count}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent Anomalies Table */}
      <div className="card">
        <div className="card__header">
          <div>
            <div className="card__title">Recent Authorization Anomalies</div>
            <div className="card__subtitle">Click any row to inspect full evidence, feature values, and AI explanation</div>
          </div>
          <button className="btn btn--ghost btn--small" onClick={() => onNavigate('ANOMALIES')}>
            View All →
          </button>
        </div>

        {predsLoading ? (
          <div className="loading-block">
            <div className="spinner" />
            <span>Loading authorization records...</span>
          </div>
        ) : predsError ? (
          <div className="error-block">
            <div className="error-block__icon">⚠</div>
            <div className="error-block__title">Unable to load anomaly records</div>
            <div className="error-block__message">{predsError}</div>
            <button className="btn btn--secondary btn--small" onClick={loadRecentAnomalies}>Retry</button>
          </div>
        ) : predictions.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state__icon">✓</div>
            <div className="empty-state__title">No anomalies in active batch</div>
            <div className="empty-state__message">All processed records passed configured validation and anomaly detection checks.</div>
          </div>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Auth / Record ID</th>
                  <th>Final Priority</th>
                  <th>ML Prediction</th>
                  <th>Anomaly Probability</th>
                  <th>SLA Urgency</th>
                  <th>Rule Triggers</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {predictions.slice(0, 8).map((item, idx) => (
                  <tr key={item.id || idx} onClick={() => onNavigate('ANOMALIES', item)}>
                    <td className="text-mono" style={{ fontWeight: 600 }}>{item.auth_id || `Record ${item.id}`}</td>
                    <td><SeverityBadge level={item.final_priority} /></td>
                    <td><PredictionBadge prediction={item.prediction} /></td>
                    <td style={{ fontWeight: 600 }}>{item.probability != null ? `${(item.probability * 100).toFixed(1)}%` : '—'}</td>
                    <td><SeverityBadge level={item.sla_risk} /></td>
                    <td>{item.rule_violations_count ?? 0}</td>
                    <td style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                      {item.timestamp ? formatTimestamp(item.timestamp) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function LegendRow({ color, label, value }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ width: 12, height: 12, borderRadius: 3, background: color, flexShrink: 0 }} />
      <span style={{ fontSize: 13, color: 'var(--text-secondary)', flex: 1 }}>{label}</span>
      <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>{value.toLocaleString()}</span>
    </div>
  );
}

export function SeverityBadge({ level }) {
  if (!level) return <span className="badge badge--low">LOW</span>;
  const cls = `badge badge--${level.toLowerCase()}`;
  return <span className={cls}>{level}</span>;
}

export function PredictionBadge({ prediction }) {
  if (!prediction) return null;
  const cls = `badge badge--${prediction.toLowerCase()}`;
  return <span className={cls}>{prediction}</span>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function computeAnomalyCategories(predictions) {
  const cats = {};
  const colorMap = {
    'ML Anomalies': '#dc2626',
    'Policy Rule Violations': '#ea580c',
    'SLA Urgency Delays': '#d97706',
    'High Risk Priority': '#7c3aed',
  };

  predictions.forEach(p => {
    if (p.prediction === 'ANOMALY') {
      const key = 'ML Anomalies';
      cats[key] = (cats[key] || 0) + 1;
    }
    if (p.rule_violations_count > 0) {
      const key = 'Policy Rule Violations';
      cats[key] = (cats[key] || 0) + 1;
    }
    if (p.sla_risk && p.sla_risk !== 'LOW') {
      const key = 'SLA Urgency Delays';
      cats[key] = (cats[key] || 0) + 1;
    }
    if (p.final_priority === 'HIGH' || p.final_priority === 'CRITICAL') {
      const key = 'High Risk Priority';
      cats[key] = (cats[key] || 0) + 1;
    }
  });

  return Object.entries(cats)
    .map(([label, count]) => ({ label, count, color: colorMap[label] || '#2563eb' }))
    .sort((a, b) => b.count - a.count);
}

function formatTimestamp(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return '—'; }
}

function formatTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return ''; }
}
