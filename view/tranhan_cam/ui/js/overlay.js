const ZONE_COLOR = '#1f5fff';

export function drawCardOverlay(card) {
  const c = card.canvas;
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
  const zone = card.cam.zone;
  if (zone && zone.length >= 3 && !card.zoneEditor.active) {
    g.beginPath();
    zone.forEach((p, idx) => {
      if (idx === 0) g.moveTo(p.x * w, p.y * h);
      else g.lineTo(p.x * w, p.y * h);
    });
    g.closePath();
    g.fillStyle = 'rgba(31, 95, 255, 0.14)';
    g.fill();
    g.lineWidth = 2;
    g.strokeStyle = ZONE_COLOR;
    g.stroke();
  }

  // 2. In-progress Zone Editor
  if (card.zoneEditor.active) {
    const pts = card.zoneEditor.points;
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
