'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Disc,
  Download,
  Loader2,
  Maximize2,
  Pentagon,
  Plus,
  RotateCcw,
  Settings,
  Trash2,
  VideoOff,
} from 'lucide-react';
import { api } from '@/lib/api';
import { CameraOverlayCanvas } from '@/components/CameraOverlayCanvas';
import { ZoneHudOverlay } from '@/components/ZoneHudOverlay';
import type { Camera, DrumZone, ZonePoint } from '@/types';

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
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [isAlert, setIsAlert] = useState(false);

  // Zone & Drum ROI Editor state
  const [editingZone, setEditingZone] = useState(false);
  const [editingDrums, setEditingDrums] = useState(false);
  const [draftPoints, setDraftPoints] = useState<ZonePoint[]>([]);
  const [draftDrums, setDraftDrums] = useState<DrumZone[]>([]);
  const [drumName, setDrumName] = useState('Cối 1');
  const [zoneBgUrl, setZoneBgUrl] = useState<string>('');
  const [savingZone, setSavingZone] = useState(false);
  const retryCountRef = useRef(0);
  const isEditingAny = editingZone || editingDrums;

  const probeLatency = useCallback(async () => {
    try {
      const res = await api.probeCamera(cam.id);
      setLatencyMs(res.latency_ms);
    } catch {
      // ignore probe errors
    }
  }, [cam.id]);

  // Refresh stream & probe when refreshNonce changes
  useEffect(() => {
    retryCountRef.current = 0;
    setStreamHealth('connecting');
    setStreamTick(Date.now());
    void probeLatency();
  }, [refreshNonce, cam.mode, cam.subtype, cam.channel, probeLatency]);

  // Periodic latency probe every 30s
  useEffect(() => {
    const id = setInterval(() => {
      void probeLatency();
    }, 30000);
    return () => clearInterval(id);
  }, [probeLatency]);

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
    setEditingDrums(false);
    setDraftDrums([]);
    setDraftPoints((cam.zone || []).map((p) => ({ ...p })));
    setZoneBgUrl(`/api/v1/cameras/${encodeURIComponent(cam.id)}/snapshot.jpg?t=${Date.now()}`);
    setEditingZone(true);
  };

  const cancelZoneEditor = () => {
    setEditingZone(false);
    setDraftPoints([]);
    setZoneBgUrl('');
  };

  const startDrumsEditor = () => {
    setEditingZone(false);
    const existing = (cam.drums || []).map((d) => ({
      ...d,
      points: d.points.map((p) => ({ ...p })),
    }));
    setDraftDrums(existing);
    setDraftPoints([]);
    setDrumName(`Cối ${existing.length + 1}`);
    setZoneBgUrl(`/api/v1/cameras/${encodeURIComponent(cam.id)}/snapshot.jpg?t=${Date.now()}`);
    setEditingDrums(true);
  };

  const cancelDrumsEditor = () => {
    setEditingDrums(false);
    setDraftDrums([]);
    setDraftPoints([]);
    setZoneBgUrl('');
  };

  const handleCommitDraftDrum = () => {
    if (draftPoints.length < 3) {
      onNotify('ROI mỗi cối cần tối thiểu 3 điểm');
      return;
    }
    const name = drumName.trim() || `Cối ${draftDrums.length + 1}`;
    const next: DrumZone[] = [
      ...draftDrums,
      { id: `drum_${Date.now() % 100000}_${draftDrums.length + 1}`, name, points: draftPoints },
    ];
    setDraftDrums(next);
    setDraftPoints([]);
    setDrumName(`Cối ${next.length + 1}`);
  };

  const handleSaveDrums = async () => {
    let finalDrums = [...draftDrums];
    if (draftPoints.length >= 3) {
      const name = drumName.trim() || `Cối ${finalDrums.length + 1}`;
      finalDrums = [
        ...finalDrums,
        { id: `drum_${Date.now() % 100000}_${finalDrums.length + 1}`, name, points: draftPoints },
      ];
    }
    setSavingZone(true);
    try {
      const updated = await api.saveDrums(cam.id, finalDrums);
      onZoneSaved(updated);
      cancelDrumsEditor();
      onNotify(`Đã lưu ${finalDrums.length} vùng cối cho ${cam.name}`);
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Lỗi lưu ROI cối');
    } finally {
      setSavingZone(false);
    }
  };

  const handleClearDrums = async () => {
    setSavingZone(true);
    try {
      const updated = await api.saveDrums(cam.id, []);
      onZoneSaved(updated);
      cancelDrumsEditor();
      onNotify(`Đã xóa toàn bộ ROI cối của ${cam.name}`);
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Lỗi xóa ROI cối');
    } finally {
      setSavingZone(false);
    }
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
    void probeLatency();
  };

  const handleStreamError = () => {
    if (streamPaused || isEditingAny) return;
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
    streamPaused || isEditingAny
      ? ''
      : cam.mode === 'snapshot'
        ? `/api/v1/cameras/${encodeURIComponent(cam.id)}/snapshot.jpg?t=${streamTick}`
        : `/api/v1/cameras/${encodeURIComponent(cam.id)}/mjpeg?subtype=${cam.subtype}&t=${streamTick}`;

  const streamModeLabel =
    cam.mode === 'snapshot'
      ? 'Snapshot'
      : `MJPEG · ${cam.subtype === 0 ? 'Chính' : 'Phụ'}`;

  return (
    <article
      className={`bg-surface-card border rounded-card p-4 md:p-5 shadow-card transition-all duration-200 hover:shadow-card-hover flex flex-col gap-3.5 ${
        isAlert && !editingZone ? 'border-status-alert/60' : 'border-line'
      }`}
    >
      {/* Tier 1: Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3
            className="text-[16px] font-semibold text-content-heading leading-snug truncate"
            title={cam.name}
          >
            {cam.name}
          </h3>
          <p
            className="text-[12px] text-content-secondary truncate mt-0.5"
            title={cam.note || `Kênh ${cam.channel}`}
          >
            Kênh {cam.channel}
            {cam.note ? ` · ${cam.note}` : ''}
          </p>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
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

          <button
            type="button"
            onClick={editingDrums ? cancelDrumsEditor : startDrumsEditor}
            className={`icon-btn ${
              editingDrums
                ? '!bg-violet-600 !text-white !border-violet-600'
                : ''
            }`}
            title={`Vẽ ROI cối xoay ${cam.name}`}
            aria-label={`Vẽ ROI cối xoay ${cam.name}`}
          >
            <Disc className="w-4 h-4" strokeWidth={1.5} />
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

      {/* Tier 2b: Conditional Drum ROI Editor Toolbar */}
      {editingDrums && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-lg bg-surface-subtle border border-line">
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="text"
              value={drumName}
              onChange={(e) => setDrumName(e.target.value)}
              placeholder="Cối 1"
              className="h-[30px] w-24 px-2 text-[12px] rounded-md border border-line bg-white text-content-heading"
            />
            <span className="text-[12px] font-medium text-content-secondary">
              Đã vẽ: {draftDrums.length} cối · đang chấm {draftPoints.length} điểm
            </span>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <button
              type="button"
              onClick={handleCommitDraftDrum}
              disabled={draftPoints.length < 3 || savingZone}
              className="btn-subtle !min-h-[30px] !px-2.5 !text-[12px]"
            >
              <Plus className="w-3.5 h-3.5" strokeWidth={1.5} />
              <span>Thêm cối</span>
            </button>
            <button
              type="button"
              onClick={() => {
                if (draftPoints.length > 0) setDraftPoints((prev) => prev.slice(0, -1));
                else if (draftDrums.length > 0) setDraftDrums((prev) => prev.slice(0, -1));
              }}
              disabled={(draftPoints.length === 0 && draftDrums.length === 0) || savingZone}
              className="btn-subtle !min-h-[30px] !px-2.5 !text-[12px]"
            >
              <RotateCcw className="w-3.5 h-3.5" strokeWidth={1.5} />
              <span>Hoàn tác</span>
            </button>
            <button
              type="button"
              onClick={handleClearDrums}
              disabled={savingZone}
              className="btn-danger !min-h-[30px] !px-2.5 !text-[12px]"
            >
              <Trash2 className="w-3.5 h-3.5" strokeWidth={1.5} />
              <span>Xóa hết</span>
            </button>
            <button
              type="button"
              onClick={handleSaveDrums}
              disabled={savingZone || (draftDrums.length === 0 && draftPoints.length < 3)}
              className="btn-primary !min-h-[30px] !px-2.5 !text-[12px]"
            >
              {savingZone && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>{savingZone ? 'Đang lưu...' : 'Lưu cối'}</span>
            </button>
            <button
              type="button"
              onClick={cancelDrumsEditor}
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
          isAlert && !isEditingAny ? 'viewport-alert-ring ring-[3px] ring-status-alert' : ''
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

        {/* Layer 2: Static Snapshot background while editing zone/drums */}
        {isEditingAny && zoneBgUrl && (
          <img
            src={zoneBgUrl}
            alt={`Ảnh nền vẽ vùng ${cam.name}`}
            className="absolute inset-0 w-full h-full object-fill select-none z-[5]"
          />
        )}

        {/* Layer 3: AI Status HUD + 30-min Rolling Timeline */}
        {!isEditingAny && (
          <ZoneHudOverlay
            cam={cam}
            compact={compact}
            onAlertStateChange={setIsAlert}
          />
        )}

        {/* Layer 4: HiDPI Canvas Overlay (0 React re-renders for BBox) */}
        <CameraOverlayCanvas
          cam={cam}
          editing={isEditingAny}
          draftPoints={draftPoints}
          draftDrums={editingDrums ? draftDrums : undefined}
          onAddPoint={(pt) => setDraftPoints((prev) => [...prev, pt])}
        />

        {/* Layer 5: Top-right Stream Health Badge */}
        {!isEditingAny && (
          <div className="absolute top-3 right-3 z-10 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-pill bg-slate-900/75 backdrop-blur-sm border border-white/10 text-[11px] font-medium text-white pointer-events-none">
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

      {/* Tier 4: Metric Row (3 clean columns, no heavy dividers) */}
      <div className="grid grid-cols-3 gap-2 pt-0.5 text-[12px]">
        <div className="min-w-0">
          <div className="text-[11px] text-content-muted">Kênh</div>
          <div className="text-[13px] font-medium text-content-primary tabular-nums truncate">
            CH {cam.channel}
          </div>
        </div>
        <div className="min-w-0">
          <div className="text-[11px] text-content-muted">Luồng</div>
          <div className="text-[13px] font-medium text-content-primary truncate">
            {streamModeLabel}
          </div>
        </div>
        <div className="min-w-0 text-right">
          <div className="text-[11px] text-content-muted">Độ trễ</div>
          <div className="text-[13px] font-medium text-content-primary tabular-nums truncate">
            {latencyMs !== null ? `${latencyMs} ms` : '—'}
          </div>
        </div>
      </div>
    </article>
  );
}
