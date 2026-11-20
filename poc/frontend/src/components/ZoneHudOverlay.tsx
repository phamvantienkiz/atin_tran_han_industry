'use client';

import { useEffect, useRef, useState } from 'react';
import { detectionStore } from '@/lib/detection-store';
import { formatMMSS } from '@/lib/zone-utils';
import type { Camera, CameraDetection, TimelineSegment, UiColor } from '@/types';

interface ZoneHudOverlayProps {
  cam: Camera;
  compact?: boolean;
  onAlertStateChange?: (isAlert: boolean) => void;
}

interface HudSnapshot {
  status: string;
  uiColor: UiColor;
  statusLabel: string;
  subLabel: string;
  alertCount: number;
  totalAlertSecInt: number;
  sessionSecInt: number;
  timeline: TimelineSegment[];
}

const ACCENT_BAR_CLASS: Record<UiColor, string> = {
  green: 'bg-status-present',
  yellow: 'bg-status-empty',
  red: 'bg-status-alert',
  idle: 'bg-status-idle',
};

const SUB_LABEL_CLASS: Record<UiColor, string> = {
  green: 'text-[#86EFAC]',
  yellow: 'text-[#FDE68A]',
  red: 'text-[#FCA5A5]',
  idle: 'text-[#BAE6FD]',
};

const SEGMENT_COLOR_HEX: Record<'green' | 'yellow' | 'red', string> = {
  green: '#22C55E',
  yellow: '#F59E0B',
  red: '#EF4444',
};

function buildSnapshot(cam: Camera, det: CameraDetection | null): HudSnapshot {
  const hasZone = (cam.zone?.length || 0) >= 3;
  if (!hasZone) {
    return {
      status: 'idle',
      uiColor: 'idle',
      statusLabel: 'CHƯA VẼ VÙNG',
      subLabel: 'Vẽ vùng giám sát để kích hoạt',
      alertCount: 0,
      totalAlertSecInt: 0,
      sessionSecInt: 0,
      timeline: [],
    };
  }
  if (!det) {
    return {
      status: 'idle',
      uiColor: 'idle',
      statusLabel: 'ĐANG KHỞI TẠO AI',
      subLabel: 'Đang chờ khung hình từ NVR...',
      alertCount: 0,
      totalAlertSecInt: 0,
      sessionSecInt: 0,
      timeline: [],
    };
  }
  return {
    status: det.status || 'empty',
    uiColor: det.ui_color || 'yellow',
    statusLabel: det.status_label || 'VÙNG TRỐNG',
    subLabel: det.sub_label || 'không có người 00:00',
    alertCount: det.alert_count || 0,
    totalAlertSecInt: Math.floor(det.total_alert_seconds || 0),
    sessionSecInt: Math.floor(det.session_duration_seconds || 0),
    timeline: det.timeline || [],
  };
}

function timelineChanged(a: TimelineSegment[], b: TimelineSegment[]): boolean {
  if (a.length !== b.length) return true;
  if (a.length === 0) return false;
  const lastA = a[a.length - 1];
  const lastB = b[b.length - 1];
  return lastA.color !== lastB.color || Math.floor(lastA.end) !== Math.floor(lastB.end);
}

export function ZoneHudOverlay({
  cam,
  compact = false,
  onAlertStateChange,
}: ZoneHudOverlayProps) {
  const [hud, setHud] = useState<HudSnapshot>(() => buildSnapshot(cam, detectionStore.get(cam.id)));
  const prevRef = useRef<HudSnapshot>(hud);
  const lastAlertRef = useRef<boolean>(hud.uiColor === 'red');
  const camRef = useRef(cam);
  camRef.current = cam;

  useEffect(() => {
    const apply = (det: CameraDetection | null) => {
      const next = buildSnapshot(camRef.current, det);
      const prev = prevRef.current;
      const changed =
        prev.status !== next.status ||
        prev.uiColor !== next.uiColor ||
        prev.statusLabel !== next.statusLabel ||
        prev.subLabel !== next.subLabel ||
        prev.alertCount !== next.alertCount ||
        prev.totalAlertSecInt !== next.totalAlertSecInt ||
        prev.sessionSecInt !== next.sessionSecInt ||
        timelineChanged(prev.timeline, next.timeline);

      if (changed) {
        prevRef.current = next;
        setHud(next);
      }

      const isAlert = next.uiColor === 'red';
      if (isAlert !== lastAlertRef.current) {
        lastAlertRef.current = isAlert;
        onAlertStateChange?.(isAlert);
      }
    };

    const unsub = detectionStore.subscribeHud(cam.id, apply);
    return () => {
      unsub();
    };
  }, [cam.id, cam.zone?.length, onAlertStateChange]);

  const zoneTitle = (cam.zone_name || cam.name).toUpperCase();
  const totalSpan =
    hud.timeline.length > 0
      ? Math.max(
          1,
          hud.timeline[hud.timeline.length - 1].end - hud.timeline[0].start,
        )
      : 1;

  return (
    <div
      className={`absolute top-2.5 left-2.5 z-10 pointer-events-none select-none bg-surface-hud rounded-md border border-white/15 shadow-md overflow-hidden text-white [text-shadow:0_1px_2px_rgba(0,0,0,0.85)] transition-colors duration-200 ${
        compact ? 'max-w-[214px] pl-2.5 pr-2 py-1.5' : 'max-w-[262px] pl-3 pr-2.5 py-2'
      }`}
    >
      {/* Left 3px semantic status accent bar */}
      <span
        aria-hidden="true"
        className={`absolute left-0 top-0 bottom-0 w-[3px] transition-colors duration-200 ${ACCENT_BAR_CLASS[hud.uiColor]}`}
      />

      {/* Row 1: Overline */}
      <div className="text-[9px] font-semibold tracking-wider uppercase text-slate-200/95 truncate">
        GIÁM SÁT NHÂN VIÊN · {zoneTitle}
      </div>

      {/* Row 2: Main Status + Dot */}
      <div className="flex items-center gap-1.5 mt-0.5">
        <span
          aria-hidden="true"
          className={`w-2 h-2 rounded-full shrink-0 transition-colors duration-200 ${ACCENT_BAR_CLASS[hud.uiColor]}`}
        />
        <span
          className={`font-bold tracking-tight text-white leading-tight truncate ${
            compact ? 'text-[12px]' : 'text-[13.5px]'
          }`}
        >
          {hud.statusLabel}
        </span>
      </div>

      {/* Row 3: Sub-label */}
      <div
        className={`font-medium mt-0.5 tabular-nums truncate ${
          compact ? 'text-[10.5px]' : 'text-[11px]'
        } ${SUB_LABEL_CLASS[hud.uiColor]}`}
      >
        {hud.subLabel}
      </div>

      {/* Row 4: KPI stats */}
      <div className="text-[10px] text-slate-200/95 mt-1 pt-1 border-t border-white/15 tabular-nums truncate">
        Tổng cảnh báo:{' '}
        <span className="font-semibold text-white">{formatMMSS(hud.totalAlertSecInt)}</span>
        {' · '}
        Số lần: <span className="font-semibold text-white">{hud.alertCount}</span>
      </div>

      {/* Row 5: Rolling 30-min Timeline */}
      <div className="mt-1">
        <div className="flex items-center justify-between text-[9px] text-slate-200/90 tabular-nums">
          <span>Timeline (30p)</span>
          <span>{formatMMSS(Math.min(1800, hud.sessionSecInt))}</span>
        </div>
        <div className="h-1 w-full bg-slate-900/65 rounded-xs overflow-hidden flex gap-[1px] mt-0.5">
          {hud.timeline.length === 0 ? (
            <div className="h-full w-full bg-slate-700/70" />
          ) : (
            hud.timeline.map((seg, idx) => {
              const segDur = Math.max(0.5, seg.end - seg.start);
              const pct = (segDur / totalSpan) * 100;
              return (
                <div
                  key={`${seg.start}-${idx}`}
                  style={{
                    width: `${pct}%`,
                    backgroundColor: SEGMENT_COLOR_HEX[seg.color],
                  }}
                  className="h-full min-w-[2px]"
                />
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
