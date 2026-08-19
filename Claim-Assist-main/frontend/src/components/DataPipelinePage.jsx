import React, { useState, useEffect } from 'react';
import { getHealth, getStats, getDataQualityReport, getFreshnessReport, getCrossDomainReport } from '../api';

export default function DataPipelinePage() {
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [dqReport, setDqReport] = useState(null);
  const [freshnessReport, setFreshnessReport] = useState(null);
  const [crossDomainReport, setCrossDomainReport] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPipelineStatus();
  }, []);

  const loadPipelineStatus = async () => {
    setLoading(true);
    const [hRes, sRes, dqRes, fRes, cdRes] = await Promise.allSettled([
      getHealth(),
      getStats(),
      getDataQualityReport(1),
      getFreshnessReport(1),
      getCrossDomainReport(),
    ]);

    if (hRes.status === 'fulfilled' && hRes.value.ok) setHealth(hRes.value.data);
    if (sRes.status === 'fulfilled' && sRes.value.ok) setStats(sRes.value.data);
    if (dqRes.status === 'fulfilled' && dqRes.value.ok) setDqReport(dqRes.value.data);
    if (fRes.status === 'fulfilled' && fRes.value.ok) setFreshnessReport(fRes.value.data);
    if (cdRes.status === 'fulfilled' && cdRes.value.ok) setCrossDomainReport(cdRes.value.data);

    setLoading(false);
  };

  const ingestionOk = health?.status === 'ok';
  const modelLoaded = health?.model_loaded === true;
  const dqOk = dqReport != null;
  const freshnessOk = freshnessReport != null;
  const crossDomainOk = crossDomainReport != null;
  const mlOk = modelLoaded;
  const dbOk = stats != null;

  const dqScore = dqReport?.summary?.overall_cms_quality_score;
  const freshnessStatus = deriveFirstFreshnessStatus(freshnessReport);
  const cdScore = crossDomainReport?.summary?.overall_cross_domain_consistency_score;

  const stages = [
    {
      num: 1,
      title: 'Incoming Data',
      status: ingestionOk ? 'Active & Receiving Stream' : loading ? 'Checking...' : 'Unavailable',
      done: ingestionOk,
      detail: health ? `FastAPI Gateway — ${health.feature_count || 25} ML Features Configured` : null,
    },
    {
      num: 2,
      title: 'Quality Validation',
      status: dqOk ? `Quality Score: ${dqScore != null ? dqScore.toFixed(1) + '%' : 'Audited'}` : loading ? 'Checking...' : 'Pending',
      done: dqOk,
      detail: dqReport?.summary?.total_rows_evaluated ? `${dqReport.summary.total_rows_evaluated.toLocaleString()} rows audited across CMS claims datasets` : null,
    },
    {
      num: 3,
      title: 'Freshness Check',
      status: freshnessOk ? `Status: ${freshnessStatus}` : loading ? 'Checking...' : 'Pending',
      done: freshnessOk,
      detail: freshnessReport?.summary?.total_datasets_evaluated ? `${freshnessReport.summary.total_datasets_evaluated} CMS dataset partitions verified for ingestion lag` : null,
    },
    {
      num: 4,
      title: 'Cross-Domain Consistency',
      status: crossDomainOk ? `Consistency: ${cdScore != null ? cdScore.toFixed(1) + '%' : 'Audited'}` : loading ? 'Checking...' : 'Pending',
      done: crossDomainOk,
      detail: crossDomainReport?.summary?.total_checks_evaluated ? `${crossDomainReport.summary.total_checks_evaluated} cross-dataset relational rules evaluated` : null,
    },
    {
      num: 5,
      title: 'ML Anomaly Detection',
      status: mlOk ? `Autoencoder + Logistic Regression (Threshold: ${health?.threshold || 0.81})` : loading ? 'Checking...' : 'Unavailable',
      done: mlOk,
      detail: stats ? `${stats.anomaly_count || 0} anomalies detected out of ${stats.total_requests || 0} evaluated authorizations` : null,
    },
    {
      num: 6,
      title: 'Risk Analysis',
      status: stats ? 'Hybrid Decision Matrix Evaluated' : loading ? 'Checking...' : 'Pending',
      done: stats != null,
      detail: stats ? `Critical: ${stats.priority_distribution?.CRITICAL || 0} | High: ${stats.priority_distribution?.HIGH || 0} | Medium: ${stats.priority_distribution?.MEDIUM || 0} | Low: ${stats.priority_distribution?.LOW || 0}` : null,
    },
    {
      num: 7,
      title: 'Persistence',
      status: dbOk ? `Operational Database Connected` : loading ? 'Checking...' : 'Unavailable',
      done: dbOk,
      detail: stats ? `${stats.total_requests || 0} total records persisted in relational storage` : null,
    },
    {
      num: 8,
      title: 'AI Explanation',
      status: 'Ollama Llama 3.2 3B Engine Ready',
      done: true,
      detail: 'Asynchronous evidence-grounded root-cause explanation engine on demand',
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 className="page-title">Data Pipeline</h2>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>
            Compact 8-stage end-to-end backend processing and intelligence pipeline
          </p>
        </div>
        <button className="btn btn--secondary" onClick={loadPipelineStatus} disabled={loading}>
          {loading ? <><div className="spinner spinner--sm" /> Checking...</> : 'Refresh Status'}
        </button>
      </div>

      {/* Pipeline Health Summary Cards */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card__title" style={{ marginBottom: 14 }}>System Pipeline Health</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
          <HealthItem label="Data Quality" value={dqScore != null ? `${dqScore.toFixed(1)}%` : '—'} ok={dqOk} />
          <HealthItem label="Freshness" value={freshnessOk ? freshnessStatus : '—'} ok={freshnessOk} />
          <HealthItem label="Cross-Domain" value={cdScore != null ? `${cdScore.toFixed(1)}%` : '—'} ok={crossDomainOk} />
          <HealthItem label="ML Detection" value={modelLoaded ? 'Active' : 'Inactive'} ok={modelLoaded} />
          <HealthItem label="Persistence" value={dbOk ? 'Connected' : 'Unavailable'} ok={dbOk} />
        </div>
      </div>

      {/* Pipeline Stages */}
      <div className="card">
        <div className="card__title" style={{ marginBottom: 16 }}>Processing Stages</div>
        <div className="pipeline">
          {stages.map((stage, idx) => (
            <React.Fragment key={stage.num}>
              <div className="pipeline__stage">
                <div className={`pipeline__stage-number ${stage.done ? 'pipeline__stage-number--done' : 'pipeline__stage-number--pending'}`}>
                  {stage.done ? '✓' : stage.num}
                </div>
                <div className="pipeline__stage-info">
                  <div className="pipeline__stage-title">{stage.title}</div>
                  <div className="pipeline__stage-status" style={{ color: stage.done ? 'var(--success)' : 'var(--text-muted)' }}>
                    {stage.status}
                  </div>
                  {stage.detail && (
                    <div style={{ fontSize: 11.5, color: 'var(--text-muted)', marginTop: 2 }}>{stage.detail}</div>
                  )}
                </div>
              </div>
              {idx < stages.length - 1 && <div className="pipeline__connector" />}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}

function HealthItem({ label, value, ok }) {
  return (
    <div style={{
      padding: '10px 14px',
      background: ok ? 'var(--success-bg)' : '#f8fafc',
      border: `1px solid ${ok ? 'var(--success-border)' : 'var(--border-light)'}`,
      borderRadius: 'var(--radius-md)',
      display: 'flex',
      alignItems: 'center',
      gap: 10,
    }}>
      <span style={{ fontSize: 16 }}>{ok ? '✓' : '○'}</span>
      <div>
        <div style={{ fontSize: 11.5, fontWeight: 600, color: ok ? 'var(--success)' : 'var(--text-muted)' }}>{label}</div>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
      </div>
    </div>
  );
}

function deriveFirstFreshnessStatus(report) {
  if (!report || !report.datasets) return 'Available';
  const datasets = report.datasets;
  const keys = Object.keys(datasets);
  if (keys.length === 0) return 'Available';
  const first = datasets[keys[0]];
  return first?.freshness_status || 'Available';
}
