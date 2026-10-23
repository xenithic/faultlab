import React, { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import Overview from './pages/Overview';
import Targets from './pages/Targets';
import Experiments from './pages/Experiments';
import ExperimentDetail from './pages/ExperimentDetail';
import { api } from './api/client';

export default function App() {
  const [currentView, setCurrentView] = useState('overview');
  const [selectedExperimentId, setSelectedExperimentId] = useState(null);

  // Platform state
  const [platformHealth, setPlatformHealth] = useState(null);
  const [targets, setTargets] = useState([]);
  const [experiments, setExperiments] = useState([]);

  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchData = useCallback(async (isBackground = false) => {
    if (!isBackground) setIsRefreshing(true);
    setError(null);

    try {
      const [healthRes, targetsRes, experimentsRes] = await Promise.allSettled([
        api.getHealth(),
        api.getTargets(),
        api.getExperiments(),
      ]);

      if (healthRes.status === 'fulfilled') {
        setPlatformHealth(healthRes.value);
      } else {
        setPlatformHealth({ status: 'unreachable', error: healthRes.reason?.message });
        setError(healthRes.reason?.message || 'Failed to connect to FaultLab platform API.');
      }

      if (targetsRes.status === 'fulfilled') {
        setTargets(targetsRes.value);
      } else if (!error) {
        setError(targetsRes.reason?.message || 'Failed to load targets.');
      }

      if (experimentsRes.status === 'fulfilled') {
        setExperiments(experimentsRes.value);
      } else if (!error) {
        setError(experimentsRes.reason?.message || 'Failed to load experiments.');
      }

      setLastUpdated(new Date());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setIsRefreshing(false);
    }
  }, [error]);

  useEffect(() => {
    fetchData(false);
  }, [fetchData]);

  // Dynamic Polling: Only poll periodically if there is at least one running experiment
  const hasRunningExperiments = experiments.some((exp) => exp.status === 'running');
  useEffect(() => {
    if (!hasRunningExperiments) return;

    const interval = setInterval(() => {
      fetchData(true);
    }, 2500);

    return () => clearInterval(interval);
  }, [hasRunningExperiments, fetchData]);

  const handleSelectExperiment = (expId) => {
    setSelectedExperimentId(expId);
    setCurrentView('experiment-detail');
  };

  const handleBackFromDetail = () => {
    setSelectedExperimentId(null);
    setCurrentView('experiments');
  };

  // Topbar titles
  const getHeaderInfo = () => {
    switch (currentView) {
      case 'overview':
        return {
          title: 'Resilience Dashboard',
          subtitle: 'Live system status, experiment metrics, and target availability',
        };
      case 'targets':
        return {
          title: 'Target Environments',
          subtitle: 'Registered Docker Compose targets and authorized service allowlists',
        };
      case 'experiments':
        return {
          title: 'Experiment Management',
          subtitle: 'Configure, execute, observe, and recover controlled chaos experiments',
        };
      case 'experiment-detail':
        return {
          title: `Experiment #${selectedExperimentId}`,
          subtitle: 'Detailed lifecycle telemetry, phase observations, and verification',
        };
      default:
        return { title: 'FaultLab', subtitle: '' };
    }
  };

  const headerInfo = getHeaderInfo();
  const runningCount = experiments.filter((e) => e.status === 'running').length;

  return (
    <div className="app-container">
      <Sidebar
        currentView={currentView}
        setCurrentView={(view) => {
          if (view !== 'experiment-detail') setSelectedExperimentId(null);
          setCurrentView(view);
        }}
        platformHealth={platformHealth}
        runningExperimentsCount={runningCount}
      />

      <div className="main-content">
        <Topbar
          title={headerInfo.title}
          subtitle={headerInfo.subtitle}
          onRefresh={() => fetchData(false)}
          isRefreshing={isRefreshing}
          lastUpdated={lastUpdated}
          error={error}
        />

        <main className="content-body">
          {currentView === 'overview' && (
            <Overview
              experiments={experiments}
              targets={targets}
              loading={loading}
              error={error}
              onSelectExperiment={handleSelectExperiment}
              onNavigate={(view) => {
                setSelectedExperimentId(null);
                setCurrentView(view);
              }}
            />
          )}

          {currentView === 'targets' && (
            <Targets
              targets={targets}
              loading={loading}
              error={error}
              onRefresh={() => fetchData(false)}
            />
          )}

          {currentView === 'experiments' && (
            <Experiments
              experiments={experiments}
              targets={targets}
              loading={loading}
              error={error}
              onRefresh={() => fetchData(false)}
              onSelectExperiment={handleSelectExperiment}
              onNavigate={(view) => {
                setSelectedExperimentId(null);
                setCurrentView(view);
              }}
            />
          )}

          {currentView === 'experiment-detail' && selectedExperimentId && (
            <ExperimentDetail
              experimentId={selectedExperimentId}
              onBack={handleBackFromDetail}
              onRefreshParent={() => fetchData(true)}
            />
          )}
        </main>
      </div>
    </div>
  );
}
