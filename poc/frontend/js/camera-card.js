import { api } from './api.js';
import { drawCardOverlay } from './overlay.js';
import { ZoneEditor } from './zone-editor.js';

const STATE_LABELS = {
  online: 'Trực tiếp',
  connecting: 'Đang kết nối',
  offline: 'Mất tín hiệu',
};

export class CameraCard {
  constructor(cam, { onEditCam, onFocusCam, onNotify }) {
    this.cam = cam;
    this.onNotify = onNotify;
    this.snapshotTimer = null;
    this.destroyed = false;
    this.detection = null;

    const subtitle = cam.note ? `Kênh ${cam.channel} · ${cam.note}` : `Kênh ${cam.channel}`;
    const streamLabel = cam.mode === 'snapshot'
      ? 'Snapshot 1.5s'
      : (cam.subtype === 0 ? 'MJPEG · Chính' : 'MJPEG · Phụ');

    this.el = document.createElement('article');
    this.el.className = 'cam-card';
    this.el.innerHTML = `
      <div class="cam-card-head">
        <div class="cam-title-block">
          <h2 class="cam-name" title="${cam.name}">${cam.name}</h2>
          <p class="cam-subtitle" title="${subtitle}">${subtitle}</p>
        </div>
        <div class="cam-actions">
          <button type="button" class="icon-btn btn-focus" title="Phóng to" aria-label="Phóng to ${cam.name}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polyline points="15 3 21 3 21 9" />
              <polyline points="9 21 3 21 3 15" />
              <line x1="21" y1="3" x2="14" y2="10" />
              <line x1="3" y1="21" x2="10" y2="14" />
            </svg>
          </button>
          <button type="button" class="icon-btn btn-zone" title="Vẽ vùng giám sát" aria-label="Vẽ vùng giám sát ${cam.name}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2" />
            </svg>
          </button>
          <a class="icon-btn btn-snap" href="/api/v1/cameras/${cam.id}/snapshot.jpg" download="${cam.id}-snapshot.jpg" title="Tải ảnh chụp nhanh" aria-label="Tải ảnh chụp nhanh ${cam.name}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
              <circle cx="12" cy="13" r="4" />
            </svg>
          </a>
          <button type="button" class="icon-btn btn-cfg" title="Cài đặt camera" aria-label="Cài đặt ${cam.name}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="1" />
              <circle cx="19" cy="12" r="1" />
              <circle cx="5" cy="12" r="1" />
            </svg>
          </button>
        </div>
      </div>

      <div class="zone-toolbar hidden">
        <span class="zone-hint">Click các điểm để vẽ vùng giám sát (tối thiểu 3 điểm).</span>
        <div class="zone-toolbar-actions">
          <button type="button" class="btn btn-subtle btn-sm z-undo">Hoàn tác</button>
          <button type="button" class="btn btn-danger btn-sm z-clear">Xóa</button>
          <button type="button" class="btn btn-primary btn-sm z-save">Lưu vùng</button>
          <button type="button" class="btn btn-subtle btn-sm z-cancel">Hủy</button>
        </div>
      </div>

      <div class="viewport">
        <img class="vid-stream" alt="Luồng trực tiếp ${cam.name}" />
        <img class="zone-bg hidden" alt="Ảnh nền vẽ vùng" />
        <canvas></canvas>
        <div class="stream-badge" data-state="connecting">
          <span class="dot"></span>
          <span class="badge-text">${STATE_LABELS.connecting}</span>
        </div>
        <div class="zone-status-badge" data-state="idle">
          <span class="dot"></span>
          <span class="zone-badge-text">${(cam.zone && cam.zone.length >= 3) ? 'Đang quét...' : 'Chưa vẽ vùng'}</span>
        </div>
        <div class="viewport-fallback hidden">
          <p>Không thể kết nối luồng video từ kênh ${cam.channel}</p>
          <button type="button" class="btn btn-subtle btn-sm btn-retry">Thử kết nối lại</button>
        </div>
      </div>

      <div class="metric-row">
        <div class="metric-col">
          <span class="metric-label">Kênh</span>
          <span class="metric-value">CH ${cam.channel}</span>
        </div>
        <div class="metric-col">
          <span class="metric-label">Luồng</span>
          <span class="metric-value">${streamLabel}</span>
        </div>
        <div class="metric-col">
          <span class="metric-label">Độ trễ</span>
          <span class="metric-value m-latency">–</span>
        </div>
      </div>
    `;

    this.streamImg = this.el.querySelector('.vid-stream');
    this.zoneBg = this.el.querySelector('.zone-bg');
    this.canvas = this.el.querySelector('canvas');
    this.badge = this.el.querySelector('.stream-badge');
    this.badgeText = this.el.querySelector('.badge-text');
    this.zoneBadge = this.el.querySelector('.zone-status-badge');
    this.zoneBadgeText = this.el.querySelector('.zone-badge-text');
    this.fallbackEl = this.el.querySelector('.viewport-fallback');
    this.latencyEl = this.el.querySelector('.m-latency');
    this.zoneToolbar = this.el.querySelector('.zone-toolbar');

    this.zoneEditor = new ZoneEditor(this, onNotify);
    this.canvas.addEventListener('click', (e) => this.zoneEditor.handleClick(e));

    this.zoneBg.addEventListener('error', () => this.zoneBg.classList.add('hidden'));
    this.streamImg.addEventListener('load', () => {
      this.setStatus('online');
      this.fallbackEl.classList.add('hidden');
      drawCardOverlay(this);
    });
    this.streamImg.addEventListener('error', () => {
      if (this.destroyed) return;
      this.setStatus('offline');
      this.fallbackEl.classList.remove('hidden');
    });

    this.el.querySelector('.btn-focus').addEventListener('click', () => onFocusCam(this.cam));
    this.el.querySelector('.btn-zone').addEventListener('click', () => this.zoneEditor.start());
    this.el.querySelector('.btn-cfg').addEventListener('click', () => onEditCam(this));
    this.el.querySelector('.btn-retry').addEventListener('click', () => this.startStream());

    this.el.querySelector('.z-undo').addEventListener('click', () => this.zoneEditor.undo());
    this.el.querySelector('.z-clear').addEventListener('click', () => this.zoneEditor.clear());
    this.el.querySelector('.z-save').addEventListener('click', () => this.zoneEditor.save());
    this.el.querySelector('.z-cancel').addEventListener('click', () => this.zoneEditor.cancel());

    this.startStream();
    this.refreshProbe();
  }

  setStatus(state) {
    this.badge.dataset.state = state;
    this.badgeText.textContent = STATE_LABELS[state] || STATE_LABELS.offline;
  }

  setDetection(det) {
    this.detection = det || null;
    if (!this.cam.zone || this.cam.zone.length < 3) {
      this.zoneBadge.dataset.state = 'idle';
      this.zoneBadgeText.textContent = 'Chưa vẽ vùng';
    } else if (!det) {
      this.zoneBadge.dataset.state = 'idle';
      this.zoneBadgeText.textContent = 'Đang quét...';
    } else if (det.error) {
      this.zoneBadge.dataset.state = 'idle';
      this.zoneBadgeText.textContent = 'Lỗi quét AI';
    } else if (det.person_in_zone) {
      this.zoneBadge.dataset.state = 'alert';
      this.zoneBadgeText.textContent = `Có người trong vùng (${det.in_zone_count})`;
    } else {
      this.zoneBadge.dataset.state = 'clear';
      this.zoneBadgeText.textContent = det.total_persons > 0
        ? `Vùng trống (${det.total_persons} ngoài vùng)`
        : 'Vùng trống';
    }
    drawCardOverlay(this);
  }

  startStream() {
    this.stopStream();
    this.setStatus('connecting');
    this.fallbackEl.classList.add('hidden');

    if (this.cam.mode === 'snapshot') {
      const loadSnap = () => {
        if (this.destroyed) return;
        this.streamImg.src = `/api/v1/cameras/${this.cam.id}/snapshot.jpg?t=${Date.now()}`;
      };
      loadSnap();
      this.snapshotTimer = setInterval(loadSnap, 1500);
    } else {
      this.streamImg.src = `/api/v1/cameras/${this.cam.id}/mjpeg?subtype=${this.cam.subtype ?? 1}&t=${Date.now()}`;
    }
  }

  stopStream() {
    if (this.snapshotTimer) {
      clearInterval(this.snapshotTimer);
      this.snapshotTimer = null;
    }
    this.streamImg.removeAttribute('src');
  }

  async refreshProbe() {
    try {
      const res = await api.probeCamera(this.cam.id);
      if (this.destroyed) return;
      if (res.online && res.latency_ms != null) {
        this.latencyEl.innerHTML = `${res.latency_ms}<span class="metric-unit">ms</span>`;
      } else {
        this.latencyEl.textContent = '–';
      }
    } catch (_) {
      if (!this.destroyed) this.latencyEl.textContent = '–';
    }
  }

  destroy() {
    this.destroyed = true;
    this.zoneEditor.stop();
    this.stopStream();
  }
}
