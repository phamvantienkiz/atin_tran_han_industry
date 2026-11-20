'use client';

import { useEffect, useRef, useState } from 'react';
import { Download, Loader2, RotateCcw, VideoOff, X } from 'lucide-react';
import { api } from '@/lib/api';
import { CameraOverlayCanvas } from '@/components/CameraOverlayCanvas';
import { ZoneHudOverlay } from '@/components/ZoneHudOverlay';
import { formatMMSS } from '@/lib/zone-utils';
import type { ActiveRecordJob, Camera } from '@/types';

interface FocusModalProps {
  cam: Camera | null;
  activeJobs: ActiveRecordJob[];
  onClose: () => void;
  onRecordsChanged: () => Promise<void>;
  onNotify: (msg: string) => void;
}

const RECORD_DURATIONS = [5, 10, 20];

export function FocusModal({
  cam,
  activeJobs,
  onClose,
  onRecordsChanged,
  onNotify,
}: FocusModalProps) {
  const [subtype, setSubtype] = useState<0 | 1>(0);
  const [streamTick, setStreamTick] = useState<number>(() => Date.now());
  const [streamError, setStreamError] = useState(false);
  const [isAlert, setIsAlert] = useState(false);
  const [recordMenuOpen, setRecordMenuOpen] = useState(false);
  const [recordBusy, setRecordBusy] = useState(false);
  const [resetBusy, setResetBusy] = useState(false);
  const retryRef = useRef(0);
  const menuWrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!cam) return;
    setSubtype(0);
    setStreamError(false);
    setRecordMenuOpen(false);
    setIsAlert(false);
    retryRef.current = 0;
    const timer = setTimeout(() => {
      setStreamTick(Date.now());
    }, 150);
    return () => clearTimeout(timer);
  }, [cam]);

  useEffect(() => {
    if (!cam) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const onDocClick = (e: MouseEvent) => {
      if (menuWrapRef.current && !menuWrapRef.current.contains(e.target as Node)) {
        setRecordMenuOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    document.addEventListener('click', onDocClick);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('click', onDocClick);
    };
  }, [cam, onClose]);

  if (!cam) return null;

  const activeJob = activeJobs.find((j) => j.cam_id === cam.id) || null;
  const streamSrc = `/api/v1/cameras/${encodeURIComponent(cam.id)}/mjpeg?subtype=${subtype}&view=focus&t=${streamTick}`;

  const handleSwitchSubtype = (nextSub: 0 | 1) => {
    setSubtype(nextSub);
    setStreamError(false);
    retryRef.current = 0;
    setStreamTick(Date.now());
  };

  const handleImageError = () => {
    if (retryRef.current < 2) {
      retryRef.current += 1;
      setTimeout(() => setStreamTick(Date.now()), 450);
    } else {
      setStreamError(true);
    }
  };

  const handleRecordClick = async () => {
    if (activeJob) {
      setRecordBusy(true);
      try {
        await api.stopRecord(cam.id);
        onNotify('Đã dừng ghi hình và lưu video MP4');
        await onRecordsChanged();
      } catch (err) {
        onNotify(err instanceof Error ? err.message : 'Lỗi dừng ghi hình');
      } finally {
        setRecordBusy(false);
      }
      return;
    }
    setRecordMenuOpen((prev) => !prev);
  };

  const handleStartRecord = async (minutes: number) => {
    setRecordMenuOpen(false);
    setRecordBusy(true);
    try {
      await api.startRecord(cam.id, minutes, subtype);
      onNotify(`Bắt đầu ghi ${cam.name} (${minutes} phút)`);
      await onRecordsChanged();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Lỗi bắt đầu ghi hình');
    } finally {
      setRecordBusy(false);
    }
  };

  const handleResetStats = async () => {
    setResetBusy(true);
    try {
      await api.resetDetectionStats(cam.id);
      onNotify(`Đã đặt lại thống kê cảnh báo cho ${cam.name}`);
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Lỗi đặt lại thống kê');
    } finally {
      setResetBusy(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="focus-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 bg-slate-900/55 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div className="bg-surface-card border border-line rounded-card shadow-2xl w-full max-w-5xl max-h-[92vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-line-muted flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2
              id="focus-modal-title"
              className="text-[18px] font-semibold text-content-heading truncate"
            >
              {cam.name}
            </h2>
            <p className="text-[12px] text-content-secondary truncate mt-0.5">
              Kênh {cam.channel}
              {cam.note ? ` · ${cam.note}` : ''}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Main / Sub stream switcher */}
            <div className="segmented-track" role="tablist" aria-label="Chất lượng luồng">
              <button
                type="button"
                role="tab"
                aria-selected={subtype === 0}
                onClick={() => handleSwitchSubtype(0)}
                className={`segmented-tab ${subtype === 0 ? 'segmented-tab-active' : ''}`}
              >
                Luồng chính
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={subtype === 1}
                onClick={() => handleSwitchSubtype(1)}
                className={`segmented-tab ${subtype === 1 ? 'segmented-tab-active' : ''}`}
              >
                Luồng phụ
              </button>
            </div>

            {/* Reset AI stats button */}
            <button
              type="button"
              onClick={handleResetStats}
              disabled={resetBusy}
              className="btn-subtle"
              title="Đặt lại bộ đếm cảnh báo và dòng thời gian"
            >
              {resetBusy ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RotateCcw className="w-4 h-4" strokeWidth={1.5} />
              )}
              <span>{resetBusy ? 'Đang đặt lại...' : 'Reset thống kê'}</span>
            </button>

            {/* Record dropdown / stop button */}
            <div ref={menuWrapRef} className="relative">
              <button
                type="button"
                onClick={handleRecordClick}
                disabled={recordBusy}
                aria-expanded={recordMenuOpen}
                aria-haspopup="menu"
                className={activeJob ? 'btn-recording' : 'btn-primary'}
              >
                {recordBusy ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <span
                    className={`w-2 h-2 rounded-full ${
                      activeJob ? 'bg-white animate-pulse' : 'bg-white/90'
                    }`}
                  />
                )}
                <span className="tabular-nums">
                  {activeJob ? `Dừng · ${formatMMSS(activeJob.remaining_sec)}` : 'Record'}
                </span>
              </button>

              {recordMenuOpen && !activeJob && (
                <div
                  role="menu"
                  aria-label="Chọn thời gian ghi hình"
                  className="absolute right-0 mt-1.5 w-36 rounded-lg bg-surface-card border border-line shadow-xl py-1 z-30"
                >
                  {RECORD_DURATIONS.map((mins) => (
                    <button
                      key={mins}
                      type="button"
                      role="menuitem"
                      onClick={() => handleStartRecord(mins)}
                      className="w-full text-left px-3.5 py-2 text-[13px] font-medium text-content-primary hover:bg-surface-subtle hover:text-content-heading transition-colors cursor-pointer"
                    >
                      {mins} phút
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Download snapshot */}
            <a
              href={`/api/v1/cameras/${encodeURIComponent(cam.id)}/snapshot.jpg`}
              download={`${cam.id}-snapshot.jpg`}
              className="btn-subtle"
            >
              <Download className="w-4 h-4" strokeWidth={1.5} />
              <span>Tải ảnh</span>
            </a>

            {/* Close button */}
            <button
              type="button"
              onClick={onClose}
              className="icon-btn"
              title="Đóng cửa sổ phóng to"
              aria-label="Đóng cửa sổ phóng to"
            >
              <X className="w-4 h-4" strokeWidth={1.5} />
            </button>
          </div>
        </div>

        {/* Viewport */}
        <div className="p-4 md:p-5 bg-surface-subtle flex-1 overflow-auto">
          <div
            className={`relative aspect-video w-full rounded-lg bg-surface-video overflow-hidden transition-shadow duration-200 ${
              isAlert ? 'viewport-alert-ring ring-[3px] ring-status-alert' : ''
            }`}
          >
            <img
              src={streamSrc}
              alt={`Luồng phóng to ${cam.name}`}
              onLoad={() => {
                retryRef.current = 0;
                setStreamError(false);
              }}
              onError={handleImageError}
              className="absolute inset-0 w-full h-full object-fill select-none"
            />

            <ZoneHudOverlay cam={cam} compact={false} onAlertStateChange={setIsAlert} />
            <CameraOverlayCanvas cam={cam} />

            {streamError && (
              <div className="absolute inset-0 z-20 bg-slate-950/85 flex flex-col items-center justify-center gap-3 p-4 text-center">
                <VideoOff className="w-7 h-7 text-slate-400" strokeWidth={1.5} />
                <p className="text-[14px] text-slate-200">
                  Không thể kết nối luồng video từ kênh CH {cam.channel}
                </p>
                <button
                  type="button"
                  onClick={() => handleSwitchSubtype(subtype)}
                  className="btn-primary"
                >
                  Thử kết nối lại
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
