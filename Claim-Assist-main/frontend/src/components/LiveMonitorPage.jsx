import React, { useState } from 'react';
import { SeverityBadge, PredictionBadge } from './OverviewDashboard';
import { simulateAuthorization } from '../api';

export default function LiveMonitorPage({ wsConnected, liveEvents, onSelectRecord, onSimulateResult }) {
  const [simulating, setSimulating] = useState(false);
  const [simError, setSimError] = useState(null);

  const handleSimulate = async () => {
    setSimulating(true);
    setSimError(null);
    const res = await simulateAuthorization();
    if (res.ok) {
      // Even if WebSocket is down, show result from HTTP response
      if (onSimulateResult) onSimulateResult(res.data);
    } else {
      setSimError(res.error);
    }
    setSimulating(false);
  };

  const connectionLabel = wsConnected ? 'System Online' : 'Reconnecting...';
  const connectionClass = wsConnected ? 'status-indicator--online' : 'status-indicator--reconnecting';
  const dotClass = wsConnected ? 'status-dot--online' : 'status-dot--reconnecting';

  return (
    <div>
      {/* Header Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 className="page-title">Live Monitor</h2>
          <p className="page-subtitle" style={{ marginBottom: 0 }}>Incoming authorization events via WebSocket</p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div className={`status-indicator ${connectionClass}`}>
            <div className={`status-dot ${dotClass}`} />
            {connectionLabel}
          </div>

          <button
            className="btn btn--primary"
            onClick={handleSimulate}
            disabled={simulating}
          >
            {simulating ? (
              <><div className="spinner spinner--sm" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} /> Simulating...</>
            ) : (
              'Simulate Authorization'
            )}
          </button>
        </div>
      </div>

      {simError && (
        <div className="card" style={{ marginBottom: 16, borderColor: 'var(--critical-border)', background: 'var(--critical-bg)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ color: 'var(--critical)', fontSize: 13, fontWeight: 500 }}>
              Simulation failed: {simError}
            </span>
            <button className="btn btn--danger btn--small" onClick={handleSimulate}>Retry</button>
          </div>
        </div>
      )}

      {/* Live Events */}
      {liveEvents.length === 0 ? (
        <div className="card">
          <div className="empty-state">
            <div className="empty-state__icon">📡</div>
            <div className="empty-state__title">No live events received yet</div>
            <div className="empty-state__message">
              Click "Simulate Authorization" above or upload a CSV to generate real-time events through the ML pipeline.
            </div>
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {liveEvents.map((evt, idx) => {
            const data = evt.data || evt;
            const pred = data.prediction || '—';
            const prio = data.final_priority || 'LOW';
            const prob = data.probability != null ? (data.probability * 100).toFixed(1) : '—';
            const ts = evt.timestamp ? formatEventTime(evt.timestamp) : '';

            return (
              <div
                key={`${data.auth_id || idx}-${idx}`}
                className={`live-event ${idx === 0 ? 'live-event--new' : ''}`}
                onClick={() => onSelectRecord && onSelectRecord(data)}
              >
                {/* Left: ID + Badges */}
                <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <span className="text-mono" style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)', minWidth: 80 }}>
                    {data.auth_id || '—'}
                  </span>
                  <PredictionBadge prediction={pred} />
                  <SeverityBadge level={prio} />
                </div>

                {/* Right: Info */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexShrink: 0 }}>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>Risk: {prob}%</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Priority: {prio}</div>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', minWidth: 70, textAlign: 'right' }}>
                    {ts}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function formatEventTime(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return ''; }
}
