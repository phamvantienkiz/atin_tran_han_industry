'use client';

import { useCallback, useEffect, useState } from 'react';
import { Download, Film, FolderArchive, Loader2, RefreshCw, Scissors, Trash2 } from 'lucide-react';
import { api } from '@/lib/api';
import { formatBytes, formatDateTime, formatMMSS } from '@/lib/zone-utils';
import type { FrameSetItem, VideoItem } from '@/types';

interface DatasetViewProps {
  refreshSignal: number;
  onNotify: (msg: string) => void;
}

export function DatasetView({ refreshSignal, onNotify }: DatasetViewProps) {
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [frameSets, setFrameSets] = useState<FrameSetItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [skipMap, setSkipMap] = useState<Record<string, 5 | 10>>({});
  const [extractingMap, setExtractingMap] = useState<Record<string, boolean>>({});
  const [deletingMap, setDeletingMap] = useState<Record<string, boolean>>({});

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [vList, fList] = await Promise.all([api.listVideos(), api.listFrameSets()]);
      setVideos(vList);
      setFrameSets(fList);
    } catch (err) {
      onNotify(
        `Lỗi tải dữ liệu lưu trữ: ${err instanceof Error ? err.message : 'Không rõ nguyên nhân'}`,
      );
    } finally {
      setLoading(false);
    }
  }, [onNotify]);

  useEffect(() => {
    void loadAll();
  }, [loadAll, refreshSignal]);

  const handleExtract = async (filename: string) => {
    const skip = skipMap[filename] ?? 5;
    setExtractingMap((prev) => ({ ...prev, [filename]: true }));
    try {
      const res = await api.extractFrames(filename, skip);
      onNotify(`Đã tách ${res.saved_frames} frame (bỏ qua ${skip} frame liên tiếp)`);
      await loadAll();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Lỗi tách frame');
    } finally {
      setExtractingMap((prev) => ({ ...prev, [filename]: false }));
    }
  };

  const handleDeleteVideo = async (filename: string) => {
    setDeletingMap((prev) => ({ ...prev, [`vid:${filename}`]: true }));
    try {
      await api.deleteVideo(filename);
      onNotify(`Đã xóa ${filename}`);
      await loadAll();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Lỗi xóa video');
    } finally {
      setDeletingMap((prev) => ({ ...prev, [`vid:${filename}`]: false }));
    }
  };

  const handleDeleteFrameSet = async (folder: string) => {
    setDeletingMap((prev) => ({ ...prev, [`fs:${folder}`]: true }));
    try {
      await api.deleteFrameSet(folder);
      onNotify(`Đã xóa ${folder}`);
      await loadAll();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Lỗi xóa bộ frame');
    } finally {
      setDeletingMap((prev) => ({ ...prev, [`fs:${folder}`]: false }));
    }
  };

  return (
    <div className="space-y-8">
      {/* Section 1: Recorded Videos */}
      <section aria-label="Video đã ghi hình" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-[20px] font-semibold text-content-heading tracking-tight">
              Video đã ghi hình
            </h2>
            <p className="text-[13px] text-content-secondary mt-0.5">
              Lưu tại storages/videos · Tải về hoặc tách frame để gán nhãn huấn luyện mô hình AI
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadAll()}
            disabled={loading}
            className="btn-subtle"
          >
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" strokeWidth={1.5} />
            )}
            <span>Làm mới danh sách</span>
          </button>
        </div>

        {videos.length === 0 ? (
          <div className="bg-surface-card border border-dashed border-line-strong rounded-card p-8 text-center text-content-secondary">
            <Film className="w-7 h-7 text-content-muted mx-auto mb-2" strokeWidth={1.5} />
            <p className="text-[14px]">
              Chưa có video nào được ghi hình. Hãy mở Phóng to một camera để bắt đầu ghi hình 5, 10
              hoặc 20 phút.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {videos.map((v) => {
              const selectedSkip = skipMap[v.filename] ?? 5;
              const isExtracting = Boolean(extractingMap[v.filename]);
              const isDeleting = Boolean(deletingMap[`vid:${v.filename}`]);
              const metaParts = [
                v.width && v.height ? `${v.width}×${v.height}` : null,
                formatMMSS(v.duration_sec),
                formatBytes(v.size_bytes),
                formatDateTime(v.created_at),
              ].filter(Boolean);

              return (
                <article
                  key={v.filename}
                  className="bg-surface-card border border-line rounded-card p-5 shadow-card hover:shadow-card-hover transition-shadow flex flex-col gap-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3
                        className="text-[15px] font-semibold text-content-heading truncate"
                        title={v.filename}
                      >
                        {v.filename}
                      </h3>
                      <p className="text-[12px] text-content-secondary mt-0.5 tabular-nums">
                        {metaParts.join(' · ')}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleDeleteVideo(v.filename)}
                      disabled={isDeleting || isExtracting}
                      className="icon-btn hover:!text-status-alert hover:!border-status-alert/40"
                      title={`Xóa video ${v.filename}`}
                      aria-label={`Xóa video ${v.filename}`}
                    >
                      {isDeleting ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" strokeWidth={1.5} />
                      )}
                    </button>
                  </div>

                  <div className="space-y-3">
                    <div className="segmented-track w-full" role="tablist" aria-label="Mức bỏ qua frame">
                      {([5, 10] as const).map((step) => (
                        <button
                          key={step}
                          type="button"
                          role="tab"
                          aria-selected={selectedSkip === step}
                          onClick={() =>
                            setSkipMap((prev) => ({ ...prev, [v.filename]: step }))
                          }
                          className={`segmented-tab flex-1 ${
                            selectedSkip === step ? 'segmented-tab-active' : ''
                          }`}
                        >
                          Bỏ qua {step} frame
                        </button>
                      ))}
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => void handleExtract(v.filename)}
                        disabled={isExtracting || isDeleting}
                        className="btn-primary w-full"
                      >
                        {isExtracting ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Scissors className="w-4 h-4" strokeWidth={1.5} />
                        )}
                        <span>{isExtracting ? 'Đang tách...' : 'Tách frame'}</span>
                      </button>

                      <a
                        href={`/api/v1/storages/videos/${encodeURIComponent(v.filename)}/download`}
                        download={v.filename}
                        className="btn-subtle w-full"
                      >
                        <Download className="w-4 h-4" strokeWidth={1.5} />
                        <span>Tải MP4</span>
                      </a>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      {/* Section 2: Extracted Frame Sets */}
      <section aria-label="Bộ frame đã tách" className="space-y-4">
        <div>
          <h2 className="text-[20px] font-semibold text-content-heading tracking-tight">
            Bộ frame đã tách
          </h2>
          <p className="text-[13px] text-content-secondary mt-0.5">
            Lưu tại storages/frames · Tải toàn bộ dưới dạng tệp nén .zip
          </p>
        </div>

        {frameSets.length === 0 ? (
          <div className="bg-surface-card border border-dashed border-line-strong rounded-card p-8 text-center text-content-secondary">
            <FolderArchive className="w-7 h-7 text-content-muted mx-auto mb-2" strokeWidth={1.5} />
            <p className="text-[14px]">
              Chưa có bộ frame nào được tách. Chọn một video phía trên và bấm Tách frame.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {frameSets.map((fs) => {
              const isDeleting = Boolean(deletingMap[`fs:${fs.folder}`]);
              const skipText = fs.skip_frames
                ? `Bỏ qua ${fs.skip_frames} frame liên tiếp`
                : 'Tất cả frame';

              return (
                <article
                  key={fs.folder}
                  className="bg-surface-card border border-line rounded-card p-5 shadow-card hover:shadow-card-hover transition-shadow flex flex-col gap-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3
                        className="text-[15px] font-semibold text-content-heading truncate"
                        title={fs.folder}
                      >
                        {fs.folder}
                      </h3>
                      <p className="text-[12px] text-content-secondary mt-0.5 tabular-nums">
                        {skipText} · {formatBytes(fs.size_bytes)}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleDeleteFrameSet(fs.folder)}
                      disabled={isDeleting}
                      className="icon-btn hover:!text-status-alert hover:!border-status-alert/40"
                      title={`Xóa bộ frame ${fs.folder}`}
                      aria-label={`Xóa bộ frame ${fs.folder}`}
                    >
                      {isDeleting ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Trash2 className="w-4 h-4" strokeWidth={1.5} />
                      )}
                    </button>
                  </div>

                  {/* Hero Metric (Soft Clean Cards × ATIN Tokens) */}
                  <div className="flex items-baseline">
                    <strong className="text-[43px] font-semibold leading-none tracking-tight text-content-heading tabular-nums">
                      {fs.frame_count}
                    </strong>
                    <span className="text-[13px] font-medium text-content-muted ml-1.5">
                      frames
                    </span>
                  </div>

                  {fs.previews && fs.previews.length > 0 && (
                    <div className="grid grid-cols-4 gap-2">
                      {fs.previews.slice(0, 4).map((img) => (
                        <img
                          key={img}
                          src={`/api/v1/storages/frames/${encodeURIComponent(fs.folder)}/preview/${encodeURIComponent(img)}`}
                          alt={img}
                          loading="lazy"
                          className="aspect-video w-full object-cover rounded-md border border-line-muted bg-slate-900"
                        />
                      ))}
                    </div>
                  )}

                  <a
                    href={`/api/v1/storages/frames/${encodeURIComponent(fs.folder)}/download.zip`}
                    download={`${fs.folder}.zip`}
                    className="btn-subtle w-full mt-auto"
                  >
                    <Download className="w-4 h-4" strokeWidth={1.5} />
                    <span>Tải bộ ảnh (.zip)</span>
                  </a>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
