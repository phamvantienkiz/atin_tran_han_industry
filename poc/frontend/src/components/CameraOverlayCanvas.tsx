'use client';

import { useCallback, useEffect, useRef } from 'react';
import { detectionStore } from '@/lib/detection-store';
import type { Camera, CameraDetection, UiColor, ZonePoint } from '@/types';

interface CameraOverlayCanvasProps {
  cam: Camera;
  editing?: boolean;
  draftPoints?: ZonePoint[];
  onAddPoint?: (point: ZonePoint) => void;
}

const COLOR_MAP: Record<UiColor, { stroke: string; fill: string }> = {
  green: { stroke: '#22C55E', fill: 'rgba(34, 197, 94, 0.14)' },
  yellow: { stroke: '#F59E0B', fill: 'rgba(245, 158, 11, 0.14)' },
  red: { stroke: '#EF4444', fill: 'rgba(239, 68, 68, 0.18)' },
  idle: { stroke: '#0284C7', fill: 'rgba(2, 132, 199, 0.14)' },
};

const BBOX_STALE_SECONDS = 3.0;

function drawRoundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + w - radius, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
  ctx.lineTo(x + w, y + h - radius);
  ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
  ctx.lineTo(x + radius, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

export function CameraOverlayCanvas({
  cam,
  editing = false,
  draftPoints = [],
  onAddPoint,
}: CameraOverlayCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const latestDetRef = useRef<CameraDetection | null>(detectionStore.get(cam.id));
  const rafIdRef = useRef<number | null>(null);

  const camRef = useRef(cam);
  const editingRef = useRef(editing);
  const draftPointsRef = useRef(draftPoints);

  camRef.current = cam;
  editingRef.current = editing;
  draftPointsRef.current = draftPoints;

  const draw = useCallback(() => {
    rafIdRef.current = null;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const targetW = Math.round(w * dpr);
    const targetH = Math.round(h * dpr);
    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW;
      canvas.height = targetH;
    }

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const currentCam = camRef.current;
    const isEditing = editingRef.current;
    const det = latestDetRef.current;

    // 1. Editing mode: draw draft polygon in brand blue with dashed closing edge
    if (isEditing) {
      const pts = draftPointsRef.current;
      if (pts.length === 0) return;

      ctx.save();
      ctx.beginPath();
      pts.forEach((pt, idx) => {
        const px = pt.x * w;
        const py = pt.y * h;
        if (idx === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      if (pts.length >= 3) {
        ctx.closePath();
        ctx.fillStyle = 'rgba(2, 132, 199, 0.16)';
        ctx.fill();
      }
      ctx.strokeStyle = '#0284C7';
      ctx.lineWidth = 2.5;
      ctx.setLineDash([6, 4]);
      ctx.stroke();
      ctx.setLineDash([]);

      pts.forEach((pt, idx) => {
        const px = pt.x * w;
        const py = pt.y * h;
        ctx.beginPath();
        ctx.arc(px, py, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = '#FFFFFF';
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = '#0284C7';
        ctx.stroke();

        ctx.font = '600 10px Inter, system-ui, sans-serif';
        ctx.fillStyle = '#FFFFFF';
        ctx.fillText(String(idx + 1), px + 7, py - 5);
      });
      ctx.restore();
      return;
    }

    // 2. Live View mode: draw saved zone polygon
    const zone = currentCam.zone || [];
    const uiColor: UiColor = zone.length >= 3 ? (det?.ui_color || 'idle') : 'idle';
    const palette = COLOR_MAP[uiColor] || COLOR_MAP.idle;

    if (zone.length >= 3) {
      ctx.save();
      ctx.beginPath();
      zone.forEach((pt, idx) => {
        const px = pt.x * w;
        const py = pt.y * h;
        if (idx === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      });
      ctx.closePath();
      ctx.fillStyle = palette.fill;
      ctx.fill();
      ctx.strokeStyle = palette.stroke;
      ctx.lineWidth = 2.5;
      ctx.lineJoin = 'round';
      ctx.stroke();

      // Vertex dots & find best vertex for Polygon Tag Pill (avoiding top-left HUD area)
      let topVertex = { x: zone[0].x * w, y: zone[0].y * h };
      let bestVisibleVertex: { x: number; y: number } | null = null;
      const hudBoxW = Math.min(230, w * 0.48);
      const hudBoxH = Math.min(120, h * 0.42);

      for (const pt of zone) {
        const px = pt.x * w;
        const py = pt.y * h;
        if (py < topVertex.y) {
          topVertex = { x: px, y: py };
        }
        const insideHud = px < hudBoxW && py < hudBoxH;
        if (!insideHud && (bestVisibleVertex === null || py < bestVisibleVertex.y)) {
          bestVisibleVertex = { x: px, y: py };
        }
        ctx.beginPath();
        ctx.arc(px, py, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#FFFFFF';
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = palette.stroke;
        ctx.stroke();
      }

      const anchorVertex = bestVisibleVertex || topVertex;
      const fallbackTitle = (currentCam.zone_name || currentCam.name).toUpperCase();
      const polyLabel = det?.polygon_label || fallbackTitle;
      if (polyLabel) {
        ctx.font = '600 10.5px Inter, system-ui, sans-serif';
        const textW = ctx.measureText(polyLabel).width;
        const padX = 7;
        const pillW = textW + padX * 2;
        const pillH = 18;
        const pillX = Math.max(8, Math.min(w - pillW - 8, anchorVertex.x - pillW / 2));
        const pillY = Math.max(8, anchorVertex.y - pillH - 6);

        drawRoundedRect(ctx, pillX, pillY, pillW, pillH, 4);
        ctx.fillStyle = palette.stroke;
        ctx.fill();

        ctx.fillStyle = '#FFFFFF';
        ctx.textBaseline = 'middle';
        ctx.fillText(polyLabel, pillX + padX, pillY + pillH / 2 + 0.5);
      }
      ctx.restore();
    }

    // 3. Anti-ghosting check before drawing Bounding Boxes (use client receipt timestamp to avoid clock skew)
    if (!det || !det.persons || det.persons.length === 0) return;
    const refTs = det._client_ts || det.updated_at || 0;
    const ageSec = Date.now() / 1000 - refTs;
    if (ageSec > BBOX_STALE_SECONDS) return;

    // 4. Draw person BBoxes (in-zone prominent green vs outside-zone dimmed slate)
    det.persons.forEach((p, idx) => {
      const bx1 = p.x1 * w;
      const by1 = p.y1 * h;
      const bw = Math.max(2, (p.x2 - p.x1) * w);
      const bh = Math.max(2, (p.y2 - p.y1) * h);
      const centerX = p.cx * w;
      const centerY = p.cy * h;
      const trackLabelId = p.track_id ?? idx + 1;

      ctx.save();
      if (p.in_zone) {
        ctx.strokeStyle = '#22C55E';
        ctx.lineWidth = 2;
        ctx.strokeRect(bx1, by1, bw, bh);

        const label = `Nhân viên #${trackLabelId}`;
        ctx.font = '600 11px Inter, system-ui, sans-serif';
        const tw = ctx.measureText(label).width;
        const padX = 6;
        const lh = 18;
        const lw = tw + padX * 2;
        const lx = Math.max(4, Math.min(w - lw - 4, bx1));
        const ly = by1 >= lh + 4 ? by1 - lh - 2 : by1 + 2;

        drawRoundedRect(ctx, lx, ly, lw, lh, 4);
        ctx.fillStyle = '#22C55E';
        ctx.fill();
        ctx.fillStyle = '#FFFFFF';
        ctx.textBaseline = 'middle';
        ctx.fillText(label, lx + padX, ly + lh / 2 + 0.5);

        // Center anchor dot
        ctx.beginPath();
        ctx.arc(centerX, centerY, 4.5, 0, Math.PI * 2);
        ctx.fillStyle = '#22C55E';
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = '#FFFFFF';
        ctx.stroke();
      } else {
        ctx.globalAlpha = 0.42;
        ctx.strokeStyle = '#94A3B8';
        ctx.lineWidth = 1.25;
        ctx.strokeRect(bx1, by1, bw, bh);

        const label = `#${trackLabelId}`;
        ctx.font = '600 10px Inter, system-ui, sans-serif';
        const tw = ctx.measureText(label).width;
        const padX = 5;
        const lh = 16;
        const lw = tw + padX * 2;
        const lx = Math.max(4, Math.min(w - lw - 4, bx1));
        const ly = by1 >= lh + 4 ? by1 - lh - 2 : by1 + 2;

        drawRoundedRect(ctx, lx, ly, lw, lh, 4);
        ctx.fillStyle = '#334155';
        ctx.fill();
        ctx.fillStyle = '#FFFFFF';
        ctx.textBaseline = 'middle';
        ctx.fillText(label, lx + padX, ly + lh / 2 + 0.5);

        ctx.beginPath();
        ctx.arc(footX, footY, 3, 0, Math.PI * 2);
        ctx.fillStyle = '#94A3B8';
        ctx.fill();
      }
      ctx.restore();
    });
  }, []);

  const scheduleDraw = useCallback(() => {
    if (rafIdRef.current !== null) return;
    rafIdRef.current = window.requestAnimationFrame(draw);
  }, [draw]);

  // Subscribe to external DetectionStore (0 React re-renders!)
  useEffect(() => {
    const unsub = detectionStore.subscribeCamera(cam.id, (det) => {
      latestDetRef.current = det;
      scheduleDraw();
    });

    // Periodic anti-ghosting sweep so stale BBoxes disappear even if stream stops sending
    const ghostTimer = setInterval(() => {
      const det = latestDetRef.current;
      const refTs = det ? det._client_ts || det.updated_at || 0 : 0;
      if (det && det.persons.length > 0 && Date.now() / 1000 - refTs > BBOX_STALE_SECONDS) {
        scheduleDraw();
      }
    }, 1000);

    return () => {
      unsub();
      clearInterval(ghostTimer);
      if (rafIdRef.current !== null) {
        window.cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, [cam.id, scheduleDraw]);

  // Redraw when zone / editing / draftPoints change
  useEffect(() => {
    scheduleDraw();
  }, [cam.zone, cam.zone_name, cam.name, editing, draftPoints, scheduleDraw]);

  // ResizeObserver keeps HiDPI canvas sharp across grid 1/4/6 changes
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => scheduleDraw());
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [scheduleDraw]);

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!editing || !onAddPoint) return;
    const rect = e.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = Math.max(0, Math.min(1, Number(((e.clientX - rect.left) / rect.width).toFixed(4))));
    const y = Math.max(0, Math.min(1, Number(((e.clientY - rect.top) / rect.height).toFixed(4))));
    onAddPoint({ x, y });
  };

  return (
    <canvas
      ref={canvasRef}
      onClick={handleClick}
      className={`absolute inset-0 w-full h-full z-[8] ${
        editing ? 'cursor-crosshair pointer-events-auto' : 'pointer-events-none'
      }`}
      aria-hidden={!editing}
    />
  );
}
