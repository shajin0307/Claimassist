import React, { useState, useEffect, useRef, useCallback, Component } from 'react';
import { API_BASE_URL, WS_URL } from './config';
import { getStats, getDataQualityReport } from './api';

import OverviewDashboard from './components/OverviewDashboard';
import LiveMonitorPage from './components/LiveMonitorPage';
import AnomaliesPage from './components/AnomaliesPage';
import DataPipelinePage from './components/DataPipelinePage';
import AnomalyDetailDrawer from './components/AnomalyDetailDrawer';
import CsvUploadModal from './components/CsvUploadModal';
import BatchSelectorBar from './components/BatchSelectorBar';
import BatchHistoryModal from './components/BatchHistoryModal';

// ============================================================================
// Error Boundary — prevents one component crash from killing the whole app
// ============================================================================
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <div className="error-boundary__title">This section could not be loaded</div>
          <div className="error-boundary__message">{this.state.error?.message || 'An unexpected error occurred.'}</div>
          <button className="btn btn--secondary" onClick={() => this.setState({ hasError: false, error: null })}>
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// ============================================================================
// Main App
// ============================================================================
export default function App() {
  const [activeTab, setActiveTab] = useState('OVERVIEW');

  // Batch isolation state
  const [selectedBatchId, setSelectedBatchId] = useState('latest');
  const [isHistoryModalOpen, setIsHistoryModalOpen] = useState(false);

  // Global data state
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState(null);
  const [dataQuality, setDataQuality] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // WebSocket
  const [wsConnected, setWsConnected] = useState(false);
  const [liveEvents, setLiveEvents] = useState([]);
  const wsRef = useRef(null);
  const wsReconnectTimer = useRef(null);
  const wsReconnectDelay = useRef(1000);

  // Modals
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [isCsvUploadOpen, setIsCsvUploadOpen] = useState(false);

  // ──────────────────────────────────────────────────────────────────
  // Data loading
  // ──────────────────────────────────────────────────────────────────
  const loadStats = useCallback(async (bId = selectedBatchId) => {
    setStatsLoading(true);
    setStatsError(null);
    const res = await getStats(bId);
    if (res.ok) {
      setStats(res.data);
      setLastRefreshed(new Date().toISOString());
    } else {
      setStatsError(res.error);
    }
    setStatsLoading(false);
  }, [selectedBatchId]);

  const loadDataQuality = useCallback(async () => {
    const res = await getDataQualityReport(1);
    if (res.ok) {
      setDataQuality(res.data);
    }
    // silently fail — DQ is non-critical for shell render
  }, []);

  const handleRefresh = useCallback(() => {
    loadStats(selectedBatchId);
    loadDataQuality();
    setRefreshTrigger(prev => prev + 1);
  }, [loadStats, loadDataQuality, selectedBatchId]);

  const handleSelectBatch = useCallback((batchId) => {
    setSelectedBatchId(batchId);
    loadStats(batchId);
    setRefreshTrigger(prev => prev + 1);
  }, [loadStats]);

  // ──────────────────────────────────────────────────────────────────
  // WebSocket
  // ──────────────────────────────────────────────────────────────────
  const connectWebSocket = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= 1) return; // already open or connecting

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      let pingInterval = null;

      ws.onopen = () => {
        setWsConnected(true);
        wsReconnectDelay.current = 1000; // reset backoff
        // Keep alive heartbeat for cloud proxies (Render/Cloudflare)
        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 15000);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.event_type === 'NEW_PREDICTION' || msg.event_type === 'BATCH_COMPLETED') {
            if (msg.event_type === 'NEW_PREDICTION') {
              setLiveEvents(prev => [msg, ...prev.slice(0, 99)]);
            }
            if (msg.event_type === 'BATCH_COMPLETED' && msg.batch_id) {
              // Automatically switch to the newly uploaded batch analysis
              setSelectedBatchId(msg.batch_id);
              loadStats(msg.batch_id);
            } else {
              loadStats(selectedBatchId);
            }
            setRefreshTrigger(prev => prev + 1);
          }
        } catch (_) { /* ignore non-JSON frames like pong */ }
      };

      ws.onclose = () => {
        if (pingInterval) clearInterval(pingInterval);
        setWsConnected(false);
        // Exponential backoff reconnect
        const delay = Math.min(wsReconnectDelay.current, 10000);
        wsReconnectTimer.current = setTimeout(() => {
          wsReconnectDelay.current = Math.min(delay * 1.5, 10000);
          connectWebSocket();
        }, delay);
      };

      ws.onerror = () => {
        if (pingInterval) clearInterval(pingInterval);
        ws.close();
      };
    } catch (_) {
      // Will retry via onclose
    }
  }, [loadStats, selectedBatchId]);

  // ──────────────────────────────────────────────────────────────────
  // Initial load
  // ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    loadStats(selectedBatchId);
    loadDataQuality();
    connectWebSocket();

    return () => {
      if (wsRef.current) wsRef.current.close();
      if (wsReconnectTimer.current) clearTimeout(wsReconnectTimer.current);
    };
  }, []);

  // ──────────────────────────────────────────────────────────────────
  // Handlers
  // ──────────────────────────────────────────────────────────────────
  const handleNavigation = useCallback((tab) => {
    setActiveTab(tab);
  }, []);

  const handleSimulateResult = useCallback((res) => {
    loadStats(selectedBatchId);
    setRefreshTrigger(prev => prev + 1);
  }, [loadStats, selectedBatchId]);

  const handleCsvSuccess = useCallback((batchResult) => {
    const newBatchId = batchResult?.summary?.batch_id || 'latest';
    setSelectedBatchId(newBatchId);
    loadStats(newBatchId);
    setRefreshTrigger(prev => prev + 1);
  }, [loadStats]);

  return (
    <div className="app-shell">
      {/* ─── Top Navigation ─── */}
      <nav className="top-nav">
        {/* Brand */}
        <div className="top-nav__brand">
          <div className="top-nav__logo">CG</div>
          <div>
            <div className="top-nav__title">ClaimGuard AI</div>
            <div className="top-nav__subtitle">Data Quality & Anomaly Monitoring</div>
          </div>
        </div>

        {/* Tabs */}
        <div className="top-nav__tabs">
          <button
            className={`top-nav__tab ${activeTab === 'OVERVIEW' ? 'top-nav__tab--active' : ''}`}
            onClick={() => setActiveTab('OVERVIEW')}
          >
            Overview
          </button>
          <button
            className={`top-nav__tab ${activeTab === 'LIVE_MONITOR' ? 'top-nav__tab--active' : ''}`}
            onClick={() => setActiveTab('LIVE_MONITOR')}
          >
            Live Monitor
          </button>
          <button
            className={`top-nav__tab ${activeTab === 'ANOMALIES' ? 'top-nav__tab--active' : ''}`}
            onClick={() => setActiveTab('ANOMALIES')}
          >
            Anomalies
          </button>
          <button
            className={`top-nav__tab ${activeTab === 'DATA_PIPELINE' ? 'top-nav__tab--active' : ''}`}
            onClick={() => setActiveTab('DATA_PIPELINE')}
          >
            Data Pipeline
          </button>
        </div>

        {/* Actions */}
        <div className="top-nav__actions">
          <div className={`status-indicator ${wsConnected ? 'status-indicator--online' : 'status-indicator--offline'}`}>
            <div className={`status-dot ${wsConnected ? 'status-dot--online' : 'status-dot--offline'}`} />
            {wsConnected ? 'System Online' : 'Reconnecting...'}
          </div>

          <button className="btn btn--secondary btn--small" onClick={handleRefresh}>
            Refresh
          </button>
          <button className="btn btn--primary btn--small" onClick={() => setIsCsvUploadOpen(true)}>
            Upload CSV
          </button>
        </div>
      </nav>

      {/* ─── Page Content ─── */}
      <main className="page-content">
        {/* Active Batch Analysis Switcher Bar */}
        <BatchSelectorBar
          selectedBatchId={selectedBatchId}
          onSelectBatch={handleSelectBatch}
          onOpenUpload={() => setIsCsvUploadOpen(true)}
          onOpenHistory={() => setIsHistoryModalOpen(true)}
          activeBatchInfo={stats?.active_batch}
          totalRecords={stats?.total_requests || 0}
        />

        {/* Backend offline banner */}
        {statsError && !stats && (
          <div className="card" style={{ marginBottom: 20, borderColor: 'var(--critical-border)', background: 'var(--critical-bg)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontWeight: 600, color: 'var(--critical)', fontSize: 14 }}>Backend unavailable</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                  Unable to connect to backend at {API_BASE_URL} — {statsError}
                </div>
              </div>
              <button className="btn btn--danger btn--small" onClick={handleRefresh}>Retry</button>
            </div>
          </div>
        )}

        <ErrorBoundary>
          {activeTab === 'OVERVIEW' && (
            <OverviewDashboard
              stats={stats || { total_requests: 0, normal_count: 0, anomaly_count: 0, priority_distribution: {} }}
              dataQuality={dataQuality}
              lastRefreshed={lastRefreshed}
              onNavigate={handleNavigation}
            />
          )}

          {activeTab === 'LIVE_MONITOR' && (
            <LiveMonitorPage
              wsConnected={wsConnected}
              liveEvents={liveEvents}
              onSelectRecord={setSelectedRecord}
              onSimulateResult={handleSimulateResult}
            />
          )}

          {activeTab === 'ANOMALIES' && (
            <AnomaliesPage
              onSelectRecord={setSelectedRecord}
              refreshTrigger={refreshTrigger}
              selectedBatchId={selectedBatchId}
            />
          )}

          {activeTab === 'DATA_PIPELINE' && (
            <DataPipelinePage />
          )}
        </ErrorBoundary>
      </main>

      {/* ─── Modals / Drawers ─── */}
      {selectedRecord && (
        <AnomalyDetailDrawer
          record={selectedRecord}
          onClose={() => setSelectedRecord(null)}
        />
      )}

      {isCsvUploadOpen && (
        <CsvUploadModal
          onClose={() => setIsCsvUploadOpen(false)}
          onBatchSuccess={handleCsvSuccess}
        />
      )}
    </div>
  );
}
