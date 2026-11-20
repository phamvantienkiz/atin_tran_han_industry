'use client';

import { Plus } from 'lucide-react';
import { CameraCard } from '@/components/CameraCard';
import type { Camera, GridLayoutCount } from '@/types';

interface CameraGridProps {
  cameras: Camera[];
  layoutCount: GridLayoutCount;
  focusedCamId: string | null;
  refreshNonce: number;
  onFocus: (cam: Camera) => void;
  onEdit: (cam: Camera) => void;
  onAdd: () => void;
  onZoneSaved: (updated: Camera) => void;
  onNotify: (msg: string) => void;
}

const GRID_COLUMNS: Record<GridLayoutCount, string> = {
  1: 'grid-cols-1 max-w-5xl mx-auto',
  4: 'grid-cols-1 lg:grid-cols-2',
  6: 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3',
};

export function CameraGrid({
  cameras,
  layoutCount,
  focusedCamId,
  refreshNonce,
  onFocus,
  onEdit,
  onAdd,
  onZoneSaved,
  onNotify,
}: CameraGridProps) {
  const emptySlotsCount = Math.max(0, layoutCount - cameras.length);

  return (
    <div className={`grid gap-5 ${GRID_COLUMNS[layoutCount]}`}>
      {cameras.map((cam) => (
        <CameraCard
          key={cam.id}
          cam={cam}
          compact={layoutCount >= 6}
          streamPaused={focusedCamId === cam.id}
          refreshNonce={refreshNonce}
          onFocus={onFocus}
          onEdit={onEdit}
          onZoneSaved={onZoneSaved}
          onNotify={onNotify}
        />
      ))}

      {Array.from({ length: emptySlotsCount }).map((_, idx) => (
        <div
          key={`empty-slot-${idx}`}
          className="min-h-[280px] rounded-card border border-dashed border-line-strong bg-surface-card/60 flex flex-col items-center justify-center gap-3 p-6 text-center"
        >
          <p className="text-[13px] text-content-muted">Chưa gán camera cho ô này</p>
          <button type="button" onClick={onAdd} className="btn-subtle">
            <Plus className="w-4 h-4" strokeWidth={1.5} />
            <span>Thêm camera</span>
          </button>
        </div>
      ))}
    </div>
  );
}
