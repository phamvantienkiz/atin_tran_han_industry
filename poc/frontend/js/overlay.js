const ZONE_COLOR = '#1f5fff';
const ALERT_COLOR = '#ef4444';
const SAFE_COLOR = '#10b981';

export function drawOverlay(c, { zone, detection, zoneEditor } = {}) {
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

  const isEditing = Boolean(zoneEditor?.active);

  // 1. Saved Poly Zone
  const personInZone = Boolean(detection?.person_in_zone);
  if (zone && zone.length >= 3 && !isEditing) {
    g.beginPath();
    zone.forEach((p, idx) => {
      if (idx === 0) g.moveTo(p.x * w, p.y * h);
      else g.lineTo(p.x * w, p.y * h);
    });
    g.closePath();
    g.fillStyle = personInZone ? 'rgba(239, 68, 68, 0.16)' : 'rgba(31, 95, 255, 0.14)';
    g.fill();
    g.lineWidth = 2;
    g.strokeStyle = personInZone ? ALERT_COLOR : ZONE_COLOR;
    g.stroke();
  }

  // 1b. Detected Person Bounding Boxes & Diagonal Center Points
  const persons = detection?.persons || [];
  if (!isEditing && persons.length > 0) {
    g.font = '600 11px Inter, system-ui, sans-serif';
    for (const p of persons) {
      const x1 = p.x1 * w;
      const y1 = p.y1 * h;
      const bw = (p.x2 - p.x1) * w;
      const bh = (p.y2 - p.y1) * h;
      const cx = p.cx * w;
      const cy = p.cy * h;
      const color = p.in_zone ? ALERT_COLOR : SAFE_COLOR;

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

      const label = `${p.in_zone ? 'Trong vùng' : 'Ngoài vùng'} ${Math.round(p.conf * 100)}%`;
      const textW = g.measureText(label).width;
      const tagY = Math.max(16, y1);
      g.fillStyle = color;
      g.fillRect(x1, tagY - 16, textW + 10, 16);
      g.fillStyle = '#ffffff';
      g.fillText(label, x1 + 5, tagY - 4);
    }
  }

  // 2. In-progress Zone Editor
  if (isEditing) {
    const pts = zoneEditor.points;
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
  drawOverlay(card.canvas, {
    zone: card.cam.zone,
    detection: card.detection,
    zoneEditor: card.zoneEditor,
  });
}

export function drawFocusOverlay(canvas, cam, detection) {
  if (!canvas || !cam) return;
  drawOverlay(canvas, {
    zone: cam.zone,
    detection,
    zoneEditor: null,
  });
}
