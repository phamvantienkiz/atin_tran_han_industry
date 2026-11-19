const ZONE_COLOR = '#1f5fff';
const ALERT_COLOR = '#ef4444';
const SAFE_COLOR = '#22c55e';
const MUTED_COLOR = '#94a3b8';

export function drawOverlay(canvas, cam, det, { active = false, points = [] } = {}) {
  const c = canvas;
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (!w || !h) return;

  const dpr = window.devicePixelRatio || 1;
  if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
    c.width = Math.round(w * dpr);
    c.height = Math.round(h * dpr);
  }

  const g = c.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);

  // 1. Saved Poly Zone
  const zone = cam.zone;
  const hasAlert = Boolean(det?.alert);
  const strokeColor = det ? (hasAlert ? ALERT_COLOR : SAFE_COLOR) : ZONE_COLOR;
  const fillColor = det
    ? (hasAlert ? 'rgba(239, 68, 68, 0.14)' : 'rgba(34, 197, 94, 0.14)')
    : 'rgba(31, 95, 255, 0.14)';

  if (zone && zone.length >= 3 && !active) {
    g.beginPath();
    zone.forEach((p, idx) => {
      if (idx === 0) g.moveTo(p.x * w, p.y * h);
      else g.lineTo(p.x * w, p.y * h);
    });
    g.closePath();
    g.fillStyle = fillColor;
    g.fill();
    g.lineWidth = 2;
    g.strokeStyle = strokeColor;
    g.stroke();

    // Vertex dots & attached zone pill when AI is active
    if (det && !det.error) {
      let anchor = zone[0];
      for (const p of zone) {
        if (p.y < anchor.y || (p.y === anchor.y && p.x < anchor.x)) anchor = p;
        g.beginPath();
        g.arc(p.x * w, p.y * h, 3.5, 0, Math.PI * 2);
        g.fillStyle = '#ffffff';
        g.fill();
        g.lineWidth = 1.5;
        g.strokeStyle = strokeColor;
        g.stroke();
      }

      const zoneTitle = det.ai_task === 'cam1_ppe'
        ? (det.violation_count > 0 ? `BẢO HỘ · THIẾU BẢO HỘ (${det.violation_count})` : 'BẢO HỘ · AN TOÀN')
        : (hasAlert
          ? `${cam.name.toUpperCase()} · KHÔNG CÓ NHÂN VIÊN`
          : `${cam.name.toUpperCase()} · CÓ NHÂN VIÊN (${det.in_zone_count})`);

      g.font = '600 10px Inter, system-ui, sans-serif';
      const tw = g.measureText(zoneTitle).width;
      const px = Math.min(Math.max(8, anchor.x * w), Math.max(8, w - tw - 22));
      const py = Math.max(22, anchor.y * h - 6);
      g.fillStyle = strokeColor;
      g.beginPath();
      g.roundRect(px, py - 16, tw + 14, 18, 4);
      g.fill();
      g.fillStyle = '#ffffff';
      g.fillText(zoneTitle, px + 7, py - 4);
    }
  }

  // 1b. Detected Bounding Boxes & Diagonal Center Points
  const persons = det?.persons || [];
  if (!active && persons.length > 0) {
    g.font = '600 11px Inter, system-ui, sans-serif';
    for (const p of persons) {
      const x1 = p.x1 * w;
      const y1 = p.y1 * h;
      const bw = (p.x2 - p.x1) * w;
      const bh = (p.y2 - p.y1) * h;
      const cx = p.cx * w;
      const cy = p.cy * h;
      const color = det?.ai_task === 'cam1_ppe'
        ? (p.is_alert ? ALERT_COLOR : SAFE_COLOR)
        : (p.in_zone ? SAFE_COLOR : MUTED_COLOR);

      g.lineWidth = 2;
      g.strokeStyle = color;
      g.strokeRect(x1, y1, bw, bh);

      // Diagonal center point
      g.beginPath();
      g.arc(cx, cy, 4, 0, Math.PI * 2);
      g.fillStyle = color;
      g.fill();
      g.lineWidth = 1.5;
      g.strokeStyle = '#ffffff';
      g.stroke();

      const tagText = p.label || (p.in_zone ? 'Trong vùng' : 'Ngoài vùng');
      const label = `${tagText} ${Math.round(p.conf * 100)}%`;
      const textW = g.measureText(label).width;
      const tagY = Math.max(16, y1);
      g.fillStyle = color;
      g.fillRect(x1, tagY - 16, textW + 10, 16);
      g.fillStyle = '#ffffff';
      g.fillText(label, x1 + 5, tagY - 4);
    }
  }

  // 2. In-progress Zone Editor
  if (active) {
    const pts = points;
    if (pts.length > 0) {
      g.beginPath();
      pts.forEach((p, idx) => {
        if (idx === 0) g.moveTo(p.x * w, p.y * h);
        else g.lineTo(p.x * w, p.y * h);
      });
      g.lineWidth = 2;
      g.strokeStyle = ZONE_COLOR;
      g.stroke();

      if (pts.length >= 2) {
        g.save();
        g.setLineDash([5, 5]);
        g.beginPath();
        g.moveTo(pts[pts.length - 1].x * w, pts[pts.length - 1].y * h);
        g.lineTo(pts[0].x * w, pts[0].y * h);
        g.stroke();
        g.restore();
      }

      if (pts.length >= 3) {
        g.beginPath();
        pts.forEach((p, idx) => {
          if (idx === 0) g.moveTo(p.x * w, p.y * h);
          else g.lineTo(p.x * w, p.y * h);
        });
        g.closePath();
        g.fillStyle = 'rgba(31, 95, 255, 0.16)';
        g.fill();
      }

      for (const p of pts) {
        g.beginPath();
        g.arc(p.x * w, p.y * h, 4.5, 0, Math.PI * 2);
        g.fillStyle = '#ffffff';
        g.fill();
        g.lineWidth = 2;
        g.strokeStyle = ZONE_COLOR;
        g.stroke();
      }
    }
  }
}

export function drawCardOverlay(card) {
  drawOverlay(card.canvas, card.cam, card.detection, card.zoneEditor);
}

function formatClock(sec) {
  const s = Math.max(0, Math.round(sec || 0));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`;
}

export function renderAiHud(hudEl, cam, det) {
  if (!hudEl) return;
  if (!det) {
    hudEl.classList.add('hidden');
    return;
  }

  hudEl.classList.remove('hidden');
  const kickerEl = hudEl.querySelector('.ai-hud-kicker');
  const statusEl = hudEl.querySelector('.ai-hud-status-text');
  const subEl = hudEl.querySelector('.ai-hud-sub');
  const statsEl = hudEl.querySelector('.ai-hud-stats');
  const elapsedEl = hudEl.querySelector('.ai-hud-elapsed');
  const timelineEl = hudEl.querySelector('.ai-hud-timeline');

  if (det.error) {
    hudEl.dataset.state = 'idle';
    kickerEl.textContent = 'GIÁM SÁT AI';
    statusEl.textContent = 'LỖI KẾT NỐI AI';
    subEl.textContent = det.error;
    return;
  }

  const durStr = formatClock(det.current_duration_sec);
  const totalAlertStr = formatClock(det.total_alert_sec);
  const alertCount = det.alert_count ?? 0;

  if (det.ai_task === 'cam1_ppe') {
    kickerEl.textContent = 'KIỂM TRA BẢO HỘ LAO ĐỘNG';
    if (det.violation_count > 0) {
      hudEl.dataset.state = 'alert';
      statusEl.textContent = `THIẾU BẢO HỘ (${det.violation_count})`;
      subEl.textContent = `Cảnh báo · vi phạm ${durStr}`;
    } else {
      hudEl.dataset.state = 'clear';
      statusEl.textContent = det.total_persons > 0 ? 'ĐỦ BẢO HỘ' : 'CHỜ ĐỐI TƯỢNG';
      subEl.textContent = `Bình thường · an toàn ${durStr}`;
    }
  } else {
    kickerEl.textContent = `GIÁM SÁT NHÂN VIÊN · ${cam.name.toUpperCase()}`;
    if (det.alert) {
      hudEl.dataset.state = 'alert';
      statusEl.textContent = 'KHÔNG CÓ NHÂN VIÊN';
      subEl.textContent = `Cảnh báo · vùng trống ${durStr}`;
    } else {
      hudEl.dataset.state = 'clear';
      statusEl.textContent = `CÓ NHÂN VIÊN (${det.in_zone_count})`;
      subEl.textContent = `Bình thường · có người ${durStr}`;
    }
  }

  statsEl.textContent = `Tổng thời gian cảnh báo: ${totalAlertStr} · Số lần cảnh báo: ${alertCount}`;
  const perfTag = det.inference_ms !== undefined ? ` · ${det.device || 'AI'} ${det.inference_ms}ms` : '';
  elapsedEl.textContent = `${durStr}${perfTag}`;
  const timeline = det.timeline || [];
  timelineEl.innerHTML = timeline
    .map((v) => `<span class="ai-hud-seg ${v ? 'is-alert' : 'is-clear'}"></span>`)
    .join('');
}
