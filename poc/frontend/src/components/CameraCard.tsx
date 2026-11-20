'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Download,
  Loader2,
  Maximize2,
  Pentagon,
  RotateCcw,
  Settings,
  Trash2,
  VideoOff,
} from 'lucide-react';
import { api } from '@/lib/api';
import { detectionStore } from '@/lib/detection-store';
import { CameraOverlayCanvas } from '@/components/CameraOverlayCanvas';
import { ZoneHudOverlay } from '@/components/ZoneHudOverlay';
import type { Camera, ZonePoint } from '@/types';

interface CameraCardProps {
  cam: Camera;
  compact: boolean;
  streamPaused: boolean;
  refreshNonce: number;
  onFocus: (cam: Camera) => void;
  onEdit: (cam: Camera) => void;
  onZoneSaved: (updated: Camera) => void;
  onNotify: (msg: string) => void;
}

type StreamHealth = 'connecting' | 'live' | 'error';

function LatencyOverlay({ camId }: { camId: string }) {
  const spanRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    let lastUpdated = 0;
    let lastText = '';
    const unsub = detectionStore.subscribeBbox(camId, (det) => {
      if (!det) return;
      const now = Date.now();
      if (now - lastUpdated < 1000) return;
      lastUpdated = now;
      const ms = det.delay_ms ?? det.inference_ms ?? null;
      const nextText = ms !== null ? `${ms} ms` : '';
      if (nextText !== lastText && spanRef.current) {
        lastText = nextText;
        spanRef.current.textContent = nextText;
      }
    });
    return () => unsub();
  }, [camId]);

  return (
    <span
      ref={spanRef}
      className="absolute bottom-2 right-2.5 z-10 pointer-events-none select-none text-[11px] font-medium text-white tabular-nums [text-shadow:0_1px_2px_rgba(0,0,0,0.9)]"
    />
  );
}

export function CameraCard({
  cam,
  compact,
  streamPaused,
  refreshNonce,
  onFocus,
  onEdit,
  onZoneSaved,
  onNotify,
}: CameraCardProps) {
  const [streamHealth, setStreamHealth] = useState<StreamHealth>('connecting');
  const [streamTick, setStreamTick] = useState<number>(() => Date.now());
  const [isAlert, setIsAlert] = useState(false);
  const [inViewport, setInViewport] = useState(true);
  const [tabHidden, setTabHidden] = useState(false);

  // Zone Editor state
  const [editingZone, setEditingZone] = useState(false);
  const [draftPoints, setDraftPoints] = useState<ZonePoint[]>([]);
  const [zoneBgUrl, setZoneBgUrl] = useState<string>('');
  const [savingZone, setSavingZone] = useState(false);
  const retryCountRef = useRef(0);
  const cardRef = useRef<HTMLElement | null>(null);

  // Refresh stream when refreshNonce changes
  useEffect(() => {
    retryCountRef.current = 0;
    setStreamHealth('connecting');
    setStreamTick(Date.now());
  }, [refreshNonce, cam.mode, cam.subtype, cam.channel]);

  // Pause stream when tab is hidden or card is scrolled out of viewport
  useEffect(() => {
    if (typeof document !== 'undefined') {
      setTabHidden(document.hidden);
      const onVis = () => setTabHidden(document.hidden);
      document.addEventListener('visibilitychange', onVis);
      const el = cardRef.current;
      let io: IntersectionObserver | null = null;
      if (el && typeof IntersectionObserver !== 'undefined') {
        io = new IntersectionObserver(
          (entries) => {
            if (entries[0]) setInViewport(entries[0].isIntersecting);
          },
          { threshold: 0.05 },
        );
        io.observe(el);
      }
      return () => {
        document.removeEventListener('visibilitychange', onVis);
        io?.disconnect();
      };
    }
    return undefined;
  }, []);

  // Snapshot polling mode when cam.mode === 'snapshot'
  useEffect(() => {
    if (cam.mode !== 'snapshot' || streamPaused || editingZone) return;
    const id = setInterval(() => {
      setStreamTick(Date.now());
    }, 1500);
    return () => clearInterval(id);
  }, [cam.mode, streamPaused, editingZone]);

  // Zone Editor keyboard shortcuts (Ctrl+Z undo, Escape cancel)
  useEffect(() => {
    if (!editingZone) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setEditingZone(false);
        setDraftPoints([]);
        setZoneBgUrl('');
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        setDraftPoints((prev) => prev.slice(0, -1));
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [editingZone]);

  const startZoneEditor = () => {
    setDraftPoints((cam.zone || []).map((p) => ({ ...p })));
    setZoneBgUrl(`/api/v1/cameras/${encodeURIComponent(cam.id)}/snapshot.jpg?t=${Date.now()}`);
    setEditingZone(true);
  };

  const cancelZoneEditor = () => {
    setEditingZone(false);
    setDraftPoints([]);
    setZoneBgUrl('');
  };

  const handleSaveZone = async () => {
    if (draftPoints.length < 3) {
      onNotify('Vùng giám sát cần tối thiểu 3 điểm');
      return;
    }
    setSavingZone(true);
    try {
      const updated = await api.saveZone(cam.id, draftPoints);
      onZoneSaved(updated);
      cancelZoneEditor();
      onNotify(`Đã lưu vùng giám sát cho ${cam.name}`);
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Lỗi lưu vùng giám sát');
    } finally {
      setSavingZone(false);
    }
  };

  const handleClearZone = async () => {
    setSavingZone(true);
    try {
      const updated = await api.saveZone(cam.id, []);
      onZoneSaved(updated);
      cancelZoneEditor();
      onNotify(`Đã xóa vùng giám sát của ${cam.name}`);
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Lỗi xóa vùng giám sát');
    } finally {
      setSavingZone(false);
    }
  };

  const reconnectStream = () => {
    retryCountRef.current = 0;
    setStreamHealth('connecting');
    setStreamTick(Date.now());
  };

  const handleStreamError = () => {
    if (streamPaused || editingZone || !inViewport || tabHidden) return;
    if (retryCountRef.current < 2) {
      retryCountRef.current += 1;
      setTimeout(() => {
        setStreamTick(Date.now());
      }, 1000);
    } else {
      setStreamHealth('error');
    }
  };

  const streamUrl =
    streamPaused || editingZone || !inViewport || tabHidden
      ? ''
      : cam.mode === 'snapshot'
        ? `/api/v1/cameras/${encodeURIComponent(cam.id)}/snapshot.jpg?t=${streamTick}`
        : `/api/v1/cameras/${encodeURIComponent(cam.id)}/mjpeg?subtype=${cam.subtype}&view=grid&t=${streamTick}`;

  return (
    <article
      ref={cardRef}
      className={`bg-surface-card border rounded-card p-4 md:p-5 shadow-card transition-all duration-200 hover:shadow-card-hover flex flex-col gap-3.5 ${
        isAlert && !editingZone ? 'border-status-alert/60' : 'border-line'
      }`}
    >
      {/* Tier 1: Header (action icons only) */}
      <div className="flex items-center justify-end gap-1.5">
          <button
            type="button"
            onClick={() => onFocus(cam)}
            className="icon-btn"
            title={`Phóng to ${cam.name}`}
            aria-label={`Phóng to ${cam.name}`}
          >
            <Maximize2 className="w-4 h-4" strokeWidth={1.5} />
          </button>

          <button
            type="button"
            onClick={editingZone ? cancelZoneEditor : startZoneEditor}
            className={`icon-btn ${
              editingZone
                ? '!bg-brand-primary !text-white !border-brand-primary'
                : ''
            }`}
            title={`Vẽ vùng giám sát ${cam.name}`}
            aria-label={`Vẽ vùng giám sát ${cam.name}`}
          >
            <Pentagon className="w-4 h-4" strokeWidth={1.5} />
          </button>

          <a
            href={`/api/v1/cameras/${encodeURIComponent(cam.id)}/snapshot.jpg`}
            download={`${cam.id}-snapshot.jpg`}
            className="icon-btn"
            title={`Tải ảnh snapshot ${cam.name}`}
            aria-label={`Tải ảnh snapshot ${cam.name}`}
          >
            <Download className="w-4 h-4" strokeWidth={1.5} />
          </a>

          <button
            type="button"
            onClick={() => onEdit(cam)}
            className="icon-btn"
            title={`Cài đặt ${cam.name}`}
            aria-label={`Cài đặt ${cam.name}`}
          >
            <Settings className="w-4 h-4" strokeWidth={1.5} />
          </button>
      </div>

      {/* Tier 2: Conditional Zone Editor Toolbar */}
      {editingZone && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-lg bg-surface-subtle border border-line">
          <span className="text-[12px] font-medium text-content-secondary">
            Click lên khung hình để chọn đỉnh vùng ({draftPoints.length} điểm · Ctrl+Z hoàn tác)
          </span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setDraftPoints((prev) => prev.slice(0, -1))}
              disabled={draftPoints.length === 0 || savingZone}
              className="btn-subtle !min-h-[30px] !px-2.5 !text-[12px]"
            >
              <RotateCcw className="w-3.5 h-3.5" strokeWidth={1.5} />
              <span>Hoàn tác</span>
            </button>
            <button
              type="button"
              onClick={handleClearZone}
              disabled={savingZone}
              className="btn-danger !min-h-[30px] !px-2.5 !text-[12px]"
            >
              <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
              <span>Xóa vùng</span>
            </button>
            <button
              type="button"
              onClick={handleSaveZone}
              disabled={savingZone || draftPoints.length < 3}
              className="btn-primary !min-h-[30px] !px-2.5 !text-[12px]"
            >
              {savingZone && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>{savingZone ? 'Đang lưu...' : 'Lưu vùng'}</span>
            </button>
            <button
              type="button"
              onClick={cancelZoneEditor}
              disabled={savingZone}
              className="btn-subtle !min-h-[30px] !px-2.5 !text-[12px]"
            >
              Hủy
            </button>
          </div>
        </div>
      )}

      {/* Tier 3: 16:9 Viewport */}
      <div
        className={`relative aspect-video w-full rounded-lg bg-surface-video overflow-hidden transition-shadow duration-200 ${
          isAlert && !editingZone ? 'viewport-alert-ring ring-[3px] ring-status-alert' : ''
        }`}
      >
        {/* Layer 1: Live MJPEG/Snapshot */}
        {streamUrl && (
          <img
            src={streamUrl}
            alt={`Luồng trực tiếp ${cam.name}`}
            onLoad={() => {
              retryCountRef.current = 0;
              setStreamHealth('live');
            }}
            onError={handleStreamError}
            className="absolute inset-0 w-full h-full object-fill select-none"
          />
        )}

        {/* Layer 2: Static Snapshot background while editing zone */}
        {editingZone && zoneBgUrl && (
          <img
            src={zoneBgUrl}
            alt={`Ảnh nền vẽ vùng ${cam.name}`}
            onError={() => {
              if (!zoneBgUrl.includes('direct=true')) {
                setZoneBgUrl(
                  `/api/v1/cameras/${encodeURIComponent(cam.id)}/snapshot.jpg?direct=true&t=${Date.now()}`,
                );
              }
            }}
            className="absolute inset-0 w-full h-full object-fill select-none z-[5]"
          />
        )}

        {/* Layer 3: AI Status HUD + 30-min Rolling Timeline */}
        {!editingZone && (
          <ZoneHudOverlay
            cam={cam}
            compact={compact}
            onAlertStateChange={setIsAlert}
          />
        )}

        {/* Layer 4: HiDPI Canvas Overlay (0 React re-renders for BBox) */}
        <CameraOverlayCanvas
          cam={cam}
          editing={editingZone}
          draftPoints={draftPoints}
          onAddPoint={(pt) => setDraftPoints((prev) => [...prev, pt])}
        />

        {/* Layer 5: Top-right Stream Health Badge */}
        {!editingZone && (
          <div className="absolute top-3 right-3 z-10 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-pill bg-slate-900/75 border border-white/10 text-[11px] font-medium text-white pointer-events-none">
            <span
              className={`w-2 h-2 rounded-full ${
                streamHealth === 'live'
                  ? 'bg-status-present'
                  : streamHealth === 'error'
                    ? 'bg-status-alert'
                    : 'bg-status-empty'
              }`}
            />
            <span>
              {streamPaused
                ? 'Đang phóng to'
                : streamHealth === 'live'
                  ? 'Trực tiếp'
                  : streamHealth === 'error'
                    ? 'Mất tín hiệu'
                    : 'Đang kết nối'}
            </span>
          </div>
        )}

        {/* Layer 5b: Bottom-right Latency (0 React re-renders, no background) */}
        {!editingZone && <LatencyOverlay camId={cam.id} />}

        {/* Stream Error Overlay */}
        {!editingZone && !streamPaused && streamHealth === 'error' && (
          <div className="absolute inset-0 z-20 bg-slate-950/85 flex flex-col items-center justify-center gap-3 p-4 text-center">
            <VideoOff className="w-6 h-6 text-slate-400" strokeWidth={1.5} />
            <p className="text-[13px] text-slate-200 max-w-xs">
              Không thể kết nối luồng video từ kênh CH {cam.channel}
            </p>
            <button
              type="button"
              onClick={reconnectStream}
              className="btn-primary !min-h-[34px] !text-[12px]"
            >
              Thử kết nối lại
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
