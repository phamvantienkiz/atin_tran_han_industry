'use client';

import { useEffect, useRef, useState } from 'react';
import { VideoOff, X } from 'lucide-react';
import { CameraOverlayCanvas } from '@/components/CameraOverlayCanvas';
import { ZoneHudOverlay } from '@/components/ZoneHudOverlay';
import type { ActiveRecordJob, Camera } from '@/types';

interface FocusModalProps {
  cam: Camera | null;
  activeJobs?: ActiveRecordJob[];
  onClose: () => void;
  onRecordsChanged?: () => Promise<void>;
  onNotify?: (msg: string) => void;
}

export function FocusModal({ cam, onClose }: FocusModalProps) {
  const [streamTick, setStreamTick] = useState<number>(() => Date.now());
  const [streamError, setStreamError] = useState(false);
  const [isAlert, setIsAlert] = useState(false);
  const retryRef = useRef(0);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const enteredFullscreenRef = useRef(false);

  useEffect(() => {
    if (!cam) return;
    setStreamError(false);
    setIsAlert(false);
    retryRef.current = 0;
    const timer = setTimeout(() => {
      setStreamTick(Date.now());
    }, 150);
    return () => clearTimeout(timer);
  }, [cam]);

  useEffect(() => {
    if (!cam) return;
    const el = containerRef.current;
    enteredFullscreenRef.current = false;

    if (el && typeof el.requestFullscreen === 'function' && !document.fullscreenElement) {
      el.requestFullscreen().catch(() => {
        // Fallback to fixed viewport fullscreen if browser blocks auto-fullscreen
      });
    }

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const onFullscreenChange = () => {
      if (document.fullscreenElement === el) {
        enteredFullscreenRef.current = true;
      } else if (enteredFullscreenRef.current && !document.fullscreenElement) {
        enteredFullscreenRef.current = false;
        onClose();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      if (el && document.fullscreenElement === el && typeof document.exitFullscreen === 'function') {
        document.exitFullscreen().catch(() => {});
      }
    };
  }, [cam, onClose]);

  if (!cam) return null;

  const streamSrc = `/api/v1/cameras/${encodeURIComponent(cam.id)}/mjpeg?subtype=0&view=focus&t=${streamTick}`;

  const handleImageError = () => {
    if (retryRef.current < 2) {
      retryRef.current += 1;
      setTimeout(() => setStreamTick(Date.now()), 450);
    } else {
      setStreamError(true);
    }
  };

  const handleReconnect = () => {
    setStreamError(false);
    retryRef.current = 0;
    setStreamTick(Date.now());
  };

  return (
    <div
      ref={containerRef}
      role="dialog"
      aria-modal="true"
      aria-label={`Xem toàn màn hình ${cam.name}`}
      className="fixed inset-0 z-50 w-screen h-screen bg-black flex items-center justify-center select-none"
    >
      <div
        className={`relative w-[min(100vw,calc(100vh*16/9))] h-[min(100vh,calc(100vw*9/16))] bg-black overflow-hidden ${
          isAlert ? 'viewport-alert-ring ring-[3px] ring-status-alert' : ''
        }`}
      >
        <img
          src={streamSrc}
          alt={`Luồng toàn màn hình ${cam.name}`}
          onLoad={() => {
            retryRef.current = 0;
            setStreamError(false);
          }}
          onError={handleImageError}
          className="absolute inset-0 w-full h-full object-fill select-none"
        />

        <ZoneHudOverlay cam={cam} compact={false} onAlertStateChange={setIsAlert} />
        <CameraOverlayCanvas cam={cam} />

        {/* Subtle Exit Fullscreen Button */}
        <button
          type="button"
          onClick={onClose}
          title="Thoát toàn màn hình (Esc)"
          aria-label="Thoát toàn màn hình"
          className="absolute top-3 right-3 z-30 w-9 h-9 rounded-full bg-black/50 hover:bg-black/80 border border-white/15 text-white flex items-center justify-center transition-colors cursor-pointer"
        >
          <X className="w-4 h-4" strokeWidth={1.75} />
        </button>

        {streamError && (
          <div className="absolute inset-0 z-20 bg-slate-950/85 flex flex-col items-center justify-center gap-3 p-4 text-center">
            <VideoOff className="w-7 h-7 text-slate-400" strokeWidth={1.5} />
            <p className="text-[14px] text-slate-200">
              Không thể kết nối luồng video từ kênh CH {cam.channel}
            </p>
            <button type="button" onClick={handleReconnect} className="btn-primary">
              Thử kết nối lại
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
