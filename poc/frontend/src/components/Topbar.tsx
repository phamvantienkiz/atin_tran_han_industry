'use client';

import { ClipboardCheck, Plus, RefreshCw } from 'lucide-react';
import { formatMMSS } from '@/lib/zone-utils';
import type { ActivePage, ActiveRecordJob, GridLayoutCount } from '@/types';

interface TopbarProps {
  nvrHost: string;
  nvrOnline: boolean | null;
  activePage: ActivePage;
  layoutCount: GridLayoutCount;
  activeJobs: ActiveRecordJob[];
  onSwitchPage: (page: ActivePage) => void;
  onChangeLayout: (count: GridLayoutCount) => void;
  onRefreshAll: () => void;
  onOpenBrief: () => void;
  onAddCamera: () => void;
}

const LAYOUT_OPTIONS: GridLayoutCount[] = [1, 4, 6];

export function Topbar({
  nvrHost,
  nvrOnline,
  activePage,
  layoutCount,
  activeJobs,
  onSwitchPage,
  onChangeLayout,
  onRefreshAll,
  onOpenBrief,
  onAddCamera,
}: TopbarProps) {
  const firstJob = activeJobs[0] || null;

  return (
    <header className="sticky top-0 z-30 min-h-[64px] bg-surface-card/90 backdrop-blur-md border-b border-line">
      <div className="max-w-[1680px] mx-auto px-4 md:px-6 py-2.5 flex flex-wrap items-center justify-between gap-3">
        {/* Left cluster: Brand + NVR status pill */}
        <div className="flex flex-wrap items-center gap-3 min-w-0">
          <div className="min-w-0">
            <h1 className="text-[16px] font-semibold text-content-heading leading-tight tracking-tight">
              ATIN Smart Fishing
            </h1>
            <p className="text-[12px] text-content-secondary leading-tight mt-0.5">
              Giám sát AI nhà máy thủy sản
            </p>
          </div>

          <span
            role="status"
            aria-live="polite"
            className="inline-flex items-center gap-2 rounded-pill px-3 py-1 bg-surface-subtle border border-line text-[12px] font-medium text-content-secondary"
          >
            <span
              aria-hidden="true"
              className={`w-2 h-2 rounded-full ${
                nvrOnline === true
                  ? 'bg-status-present'
                  : nvrOnline === false
                    ? 'bg-status-alert'
                    : 'bg-status-empty'
              }`}
            />
            <span className="truncate max-w-[200px]">{nvrHost || 'Chưa cấu hình NVR'}</span>
          </span>
        </div>

        {/* Right cluster: Page Switcher + Recording Pill + Live View Controls */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="segmented-track" role="tablist" aria-label="Chuyển trang">
            <button
              type="button"
              role="tab"
              aria-selected={activePage === 'live'}
              onClick={() => onSwitchPage('live')}
              className={`segmented-tab ${activePage === 'live' ? 'segmented-tab-active' : ''}`}
            >
              Live view
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={activePage === 'dataset'}
              onClick={() => onSwitchPage('dataset')}
              className={`segmented-tab ${activePage === 'dataset' ? 'segmented-tab-active' : ''}`}
            >
              Video &amp; Tách frame
            </button>
          </div>

          {firstJob && (
            <span
              role="status"
              aria-live="polite"
              className="inline-flex items-center gap-2 rounded-pill px-3 py-1 bg-status-alert/10 text-status-alert border border-status-alert/30 text-[12px] font-medium tabular-nums"
            >
              <span className="w-2 h-2 rounded-full bg-status-alert animate-pulse" />
              <span>
                Đang ghi CH {firstJob.channel} · còn {formatMMSS(firstJob.remaining_sec)}
              </span>
            </span>
          )}

          {activePage === 'live' && (
            <div className="flex flex-wrap items-center gap-2">
              <div className="segmented-track" role="tablist" aria-label="Bố cục lưới camera">
                {LAYOUT_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    role="tab"
                    aria-selected={layoutCount === opt}
                    onClick={() => onChangeLayout(opt)}
                    className={`segmented-tab min-w-[34px] ${
                      layoutCount === opt ? 'segmented-tab-active' : ''
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={onRefreshAll}
                className="btn-subtle"
                title="Kết nối lại toàn bộ camera"
              >
                <RefreshCw className="w-4 h-4" strokeWidth={1.5} />
                <span>Làm mới</span>
              </button>

              <button type="button" onClick={onOpenBrief} className="btn-subtle">
                <ClipboardCheck className="w-4 h-4" strokeWidth={1.5} />
                <span>Bài toán AI</span>
              </button>

              <button type="button" onClick={onAddCamera} className="btn-primary">
                <Plus className="w-4 h-4" strokeWidth={1.75} />
                <span>Thêm camera</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
