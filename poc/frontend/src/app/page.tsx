'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AiBriefModal } from '@/components/AiBriefModal';
import { CameraFormModal } from '@/components/CameraFormModal';
import { CameraGrid } from '@/components/CameraGrid';
import { DatasetView } from '@/components/DatasetView';
import { FocusModal } from '@/components/FocusModal';
import { Toast } from '@/components/Toast';
import { Topbar } from '@/components/Topbar';
import { api } from '@/lib/api';
import { detectionsWsClient } from '@/lib/ws-client';
import type { ActivePage, ActiveRecordJob, Camera, GridLayoutCount } from '@/types';

const LAYOUT_STORAGE_KEY = 'tranhan_grid_layout';

export default function HomePage() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [nvrHost, setNvrHost] = useState<string>('nmts2025.smartddns.tv');
  const [nvrOnline, setNvrOnline] = useState<boolean | null>(null);
  const [activePage, setActivePage] = useState<ActivePage>('live');
  const [layoutCount, setLayoutCount] = useState<GridLayoutCount>(4);
  const [refreshNonce, setRefreshNonce] = useState<number>(0);
  const [datasetRefreshSignal, setDatasetRefreshSignal] = useState<number>(0);

  const [focusedCam, setFocusedCam] = useState<Camera | null>(null);
  const [camModalOpen, setCamModalOpen] = useState(false);
  const [editingCam, setEditingCam] = useState<Camera | null>(null);
  const [briefModalOpen, setBriefModalOpen] = useState(false);

  const [activeJobs, setActiveJobs] = useState<ActiveRecordJob[]>([]);
  const hadActiveJobsRef = useRef(false);

  const [toastMsg, setToastMsg] = useState<string | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const showToast = useCallback((msg: string) => {
    setToastMsg(msg);
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => {
      setToastMsg(null);
    }, 3000);
  }, []);

  const loadCameras = useCallback(async () => {
    try {
      const list = await api.cameras();
      list.sort((a, b) => a.channel - b.channel);
      setCameras(list);

      if (list.length > 0) {
        const probe = await api.probeCamera(list[0].id).catch(() => ({ online: false }));
        setNvrOnline(Boolean(probe.online));
      } else {
        setNvrOnline(null);
      }
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Không thể tải danh sách camera');
    }
  }, [showToast]);

  const pollActiveRecords = useCallback(async () => {
    try {
      const jobs = await api.activeRecords();
      if (hadActiveJobsRef.current && jobs.length === 0) {
        showToast('Đã hoàn tất ghi hình video');
        setDatasetRefreshSignal((n) => n + 1);
      }
      hadActiveJobsRef.current = jobs.length > 0;
      setActiveJobs(jobs);
    } catch {
      // ignore transient poll errors
    }
  }, [showToast]);

  // Initial bootstrap: layout preference, config, cameras, WebSocket detections, record polling
  useEffect(() => {
    const savedLayout = Number(window.localStorage.getItem(LAYOUT_STORAGE_KEY));
    if (savedLayout === 1 || savedLayout === 4 || savedLayout === 6) {
      setLayoutCount(savedLayout);
    }

    let wsPath = '/api/v1/ws/detections';
    api
      .config()
      .then((cfg) => {
        if (cfg.nvr_host) setNvrHost(cfg.nvr_host);
        if (cfg.ws_path) wsPath = cfg.ws_path;
      })
      .catch(() => {})
      .finally(() => {
        detectionsWsClient.start(wsPath);
      });

    void loadCameras();
    void pollActiveRecords();

    const recTimer = setInterval(() => {
      void pollActiveRecords();
    }, 1000);

    return () => {
      clearInterval(recTimer);
      detectionsWsClient.stop();
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, [loadCameras, pollActiveRecords]);

  const handleChangeLayout = (count: GridLayoutCount) => {
    setLayoutCount(count);
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, String(count));
  };

  const handleSwitchPage = (page: ActivePage) => {
    setActivePage(page);
    if (page === 'dataset') {
      setDatasetRefreshSignal((n) => n + 1);
    }
  };

  const handleRefreshAll = () => {
    setRefreshNonce((n) => n + 1);
    void loadCameras();
    showToast('Đang kết nối lại toàn bộ camera');
  };

  const handleOpenFocus = (cam: Camera) => {
    setFocusedCam(cam);
    detectionsWsClient.setFocus(cam.id);
  };

  const handleCloseFocus = useCallback(() => {
    setFocusedCam(null);
    detectionsWsClient.setFocus(null);
  }, []);

  const handleZoneSaved = (updated: Camera) => {
    setCameras((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
    setFocusedCam((prev) => (prev && prev.id === updated.id ? updated : prev));
  };

  return (
    <div className="min-h-screen flex flex-col">
      <Topbar
        nvrHost={nvrHost}
        nvrOnline={nvrOnline}
        activePage={activePage}
        layoutCount={layoutCount}
        activeJobs={activeJobs}
        onSwitchPage={handleSwitchPage}
        onChangeLayout={handleChangeLayout}
        onRefreshAll={handleRefreshAll}
        onOpenBrief={() => setBriefModalOpen(true)}
        onAddCamera={() => {
          setEditingCam(null);
          setCamModalOpen(true);
        }}
      />

      <main className="flex-1 w-full max-w-[1680px] mx-auto px-4 md:px-6 py-6">
        {activePage === 'live' ? (
          <section aria-label="Danh sách camera trực tiếp">
            <CameraGrid
              cameras={cameras}
              layoutCount={layoutCount}
              focusedCamId={focusedCam?.id || null}
              refreshNonce={refreshNonce}
              onFocus={handleOpenFocus}
              onEdit={(cam) => {
                setEditingCam(cam);
                setCamModalOpen(true);
              }}
              onAdd={() => {
                setEditingCam(null);
                setCamModalOpen(true);
              }}
              onZoneSaved={handleZoneSaved}
              onNotify={showToast}
            />
          </section>
        ) : (
          <section aria-label="Quản lý video và tách frame">
            <DatasetView refreshSignal={datasetRefreshSignal} onNotify={showToast} />
          </section>
        )}
      </main>

      <FocusModal
        cam={focusedCam}
        activeJobs={activeJobs}
        onClose={handleCloseFocus}
        onRecordsChanged={pollActiveRecords}
        onNotify={showToast}
      />

      <CameraFormModal
        open={camModalOpen}
        camera={editingCam}
        onClose={() => setCamModalOpen(false)}
        onSaved={loadCameras}
        onNotify={showToast}
      />

      <AiBriefModal open={briefModalOpen} onClose={() => setBriefModalOpen(false)} />

      <Toast message={toastMsg} />
    </div>
  );
}
