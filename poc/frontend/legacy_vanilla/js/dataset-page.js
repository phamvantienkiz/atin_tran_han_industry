import { api } from './api.js';

function formatBytes(bytes) {
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

function formatDuration(sec) {
  const s = Math.max(0, Math.round(sec || 0));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${String(m).padStart(2, '0')}:${String(rem).padStart(2, '0')}`;
}

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleString('vi-VN', {
    hour12: false,
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const TRASH_ICON = `
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6" />
    <path d="M14 11v6" />
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </svg>
`;

export class DatasetPage {
  constructor(videosGrid, framesGrid, onNotify) {
    this.videosGrid = videosGrid;
    this.framesGrid = framesGrid;
    this.onNotify = onNotify;
    this.skipMap = {};
  }

  async refresh() {
    try {
      const [videos, frameSets] = await Promise.all([
        api.listVideos(),
        api.listFrameSets(),
      ]);
      this.renderVideos(videos);
      this.renderFrameSets(frameSets);
    } catch (err) {
      this.onNotify(`Lỗi tải dữ liệu lưu trữ: ${err.message}`);
    }
  }

  renderVideos(videos) {
    this.videosGrid.innerHTML = '';
    if (!videos.length) {
      this.videosGrid.innerHTML =
        '<div class="empty-state">Chưa có video nào được ghi hình. Hãy mở Phóng to một camera để bắt đầu ghi hình 5, 10 hoặc 20 phút.</div>';
      return;
    }

    for (const v of videos) {
      const selectedSkip = this.skipMap[v.filename] || 5;
      const card = document.createElement('article');
      card.className = 'data-card';
      const metaParts = [
        v.width && v.height ? `${v.width}×${v.height}` : null,
        formatDuration(v.duration_sec),
        formatBytes(v.size_bytes),
        formatDate(v.created_at),
      ].filter(Boolean);

      card.innerHTML = `
        <div class="data-card-head">
          <div style="min-width:0">
            <h3 class="data-card-title">${v.filename}</h3>
            <p class="data-card-sub">${metaParts.join(' · ')}</p>
          </div>
          <button type="button" class="icon-btn btn-del-video" title="Xóa video" aria-label="Xóa ${v.filename}">
            ${TRASH_ICON}
          </button>
        </div>

        <div class="data-card-controls">
          <div class="segmented" role="tablist" aria-label="Mức bỏ qua frame">
            <button type="button" role="tab" aria-selected="${selectedSkip === 5}" class="seg-btn" data-skip="5">Bỏ qua 5 frame</button>
            <button type="button" role="tab" aria-selected="${selectedSkip === 10}" class="seg-btn" data-skip="10">Bỏ qua 10 frame</button>
          </div>
          <div class="data-card-actions">
            <button type="button" class="btn btn-primary btn-extract">Tách frame</button>
            <a class="btn btn-subtle" href="/api/v1/storages/videos/${encodeURIComponent(v.filename)}/download" download="${v.filename}">Tải MP4</a>
          </div>
        </div>
      `;

      card.querySelectorAll('[data-skip]').forEach((btn) => {
        btn.addEventListener('click', () => {
          const skip = Number(btn.dataset.skip);
          this.skipMap[v.filename] = skip;
          card.querySelectorAll('[data-skip]').forEach((b) => {
            b.setAttribute('aria-selected', String(Number(b.dataset.skip) === skip));
          });
        });
      });

      const extractBtn = card.querySelector('.btn-extract');
      extractBtn.addEventListener('click', async () => {
        const skip = this.skipMap[v.filename] || 5;
        extractBtn.disabled = true;
        extractBtn.textContent = 'Đang tách...';
        try {
          const res = await api.extractFrames(v.filename, skip);
          this.onNotify(`Đã tách ${res.saved_frames} frame (bỏ qua ${skip} frame liên tiếp)`);
          await this.refresh();
        } catch (err) {
          this.onNotify(err.message);
        } finally {
          extractBtn.disabled = false;
          extractBtn.textContent = 'Tách frame';
        }
      });

      card.querySelector('.btn-del-video').addEventListener('click', async () => {
        try {
          await api.deleteVideo(v.filename);
          this.onNotify(`Đã xóa ${v.filename}`);
          await this.refresh();
        } catch (err) {
          this.onNotify(err.message);
        }
      });

      this.videosGrid.appendChild(card);
    }
  }

  renderFrameSets(frameSets) {
    this.framesGrid.innerHTML = '';
    if (!frameSets.length) {
      this.framesGrid.innerHTML =
        '<div class="empty-state">Chưa có bộ frame nào được tách. Chọn một video phía trên và bấm Tách frame.</div>';
      return;
    }

    for (const fs of frameSets) {
      const card = document.createElement('article');
      card.className = 'data-card';
      const skipText = fs.skip_frames ? `Bỏ qua ${fs.skip_frames} frame liên tiếp` : 'Tất cả frame';
      const thumbsHtml = (fs.previews || [])
        .map(
          (img) =>
            `<img src="/api/v1/storages/frames/${encodeURIComponent(fs.folder)}/preview/${encodeURIComponent(img)}" alt="${img}" loading="lazy" />`,
        )
        .join('');

      card.innerHTML = `
        <div class="data-card-head">
          <div style="min-width:0">
            <h3 class="data-card-title">${fs.folder}</h3>
            <p class="data-card-sub">${skipText} · ${formatBytes(fs.size_bytes)}</p>
          </div>
          <button type="button" class="icon-btn btn-del-frames" title="Xóa bộ frame" aria-label="Xóa ${fs.folder}">
            ${TRASH_ICON}
          </button>
        </div>

        <div class="hero-metric">
          <strong class="hero-num">${fs.frame_count}</strong>
          <span class="hero-unit">frames</span>
        </div>

        ${thumbsHtml ? `<div class="thumb-strip">${thumbsHtml}</div>` : ''}

        <a class="btn btn-subtle btn-full" href="/api/v1/storages/frames/${encodeURIComponent(fs.folder)}/download.zip" download="${fs.folder}.zip">
          Tải bộ ảnh (.zip)
        </a>
      `;

      card.querySelector('.btn-del-frames').addEventListener('click', async () => {
        try {
          await api.deleteFrameSet(fs.folder);
          this.onNotify(`Đã xóa ${fs.folder}`);
          await this.refresh();
        } catch (err) {
          this.onNotify(err.message);
        }
      });

      this.framesGrid.appendChild(card);
    }
  }
}
