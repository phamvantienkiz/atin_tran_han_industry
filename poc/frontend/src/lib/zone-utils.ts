import type { ZonePoint } from '@/types';

export function parseZoneJson(rawText: string): ZonePoint[] {
  const parsed = JSON.parse(rawText);

  if (Array.isArray(parsed)) {
    return parsed.map((p) => {
      if (Array.isArray(p) && p.length >= 2) {
        return clampPoint(Number(p[0]), Number(p[1]));
      }
      if (p && typeof p === 'object' && 'x' in p && 'y' in p) {
        return clampPoint(Number(p.x), Number(p.y));
      }
      throw new Error('Mỗi điểm trong JSON phải có tọa độ x, y hợp lệ');
    });
  }

  if (parsed && Array.isArray(parsed.points) && parsed.image_width && parsed.image_height) {
    const w = Number(parsed.image_width);
    const h = Number(parsed.image_height);
    if (!w || !h) throw new Error('image_width / image_height không hợp lệ');
    return parsed.points.map((p: { x: number; y: number }) =>
      clampPoint(Number((Number(p.x) / w).toFixed(4)), Number((Number(p.y) / h).toFixed(4))),
    );
  }

  throw new Error('Định dạng JSON zone không hợp lệ');
}

function clampPoint(x: number, y: number): ZonePoint {
  if (Number.isNaN(x) || Number.isNaN(y)) {
    throw new Error('Tọa độ zone chứa giá trị không phải số');
  }
  return {
    x: Math.max(0, Math.min(1, Number(x.toFixed(4)))),
    y: Math.max(0, Math.min(1, Number(y.toFixed(4)))),
  };
}

export function formatMMSS(sec: number | null | undefined): string {
  const s = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${String(m).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let val = bytes;
  let i = 0;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i += 1;
  }
  return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatDateTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString('vi-VN', {
    hour12: false,
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}
