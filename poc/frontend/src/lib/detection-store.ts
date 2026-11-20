import type { BboxWsMessage, CameraDetection, HudWsMessage } from '@/types';

type CameraListener = (det: CameraDetection | null) => void;

class DetectionStore {
  private data: Record<string, CameraDetection> = {};
  private bboxListeners: Map<string, Set<CameraListener>> = new Map();
  private hudListeners: Map<string, Set<CameraListener>> = new Map();
  private bboxStaleSeconds = 0.7;

  setBboxStaleSeconds(sec: number): void {
    if (Number.isFinite(sec) && sec > 0.1) {
      this.bboxStaleSeconds = sec;
    }
  }

  getBboxStaleSeconds(): number {
    return this.bboxStaleSeconds;
  }

  updateBbox(msg: BboxWsMessage): void {
    const camId = msg.cam_id;
    if (!camId) return;
    const nowSec = Date.now() / 1000;
    const prev = this.data[camId];
    const next: CameraDetection = {
      cam_id: camId,
      has_zone: prev?.has_zone ?? true,
      person_in_zone: (msg.in_zone_count ?? 0) > 0,
      in_zone_count: msg.in_zone_count ?? prev?.in_zone_count ?? 0,
      total_persons: msg.persons?.length ?? 0,
      persons: msg.persons || [],
      status: prev?.status ?? 'empty',
      ui_color: prev?.ui_color ?? 'yellow',
      status_label: prev?.status_label ?? 'VÙNG TRỐNG',
      sub_label: prev?.sub_label ?? 'không có người 00:00',
      polygon_label: prev?.polygon_label ?? '',
      empty_duration: prev?.empty_duration ?? 0,
      alert_count: prev?.alert_count ?? 0,
      total_alert_seconds: prev?.total_alert_seconds ?? 0,
      session_duration_seconds: prev?.session_duration_seconds ?? 0,
      timeline: prev?.timeline ?? [],
      inference_ms: msg.inference_ms ?? prev?.inference_ms,
      delay_ms: msg.delay_ms ?? prev?.delay_ms,
      active_provider: prev?.active_provider,
      updated_at: msg.ts_capture ?? nowSec,
      _client_ts: nowSec,
    };
    this.data[camId] = next;
    this.bboxListeners.get(camId)?.forEach((fn) => fn(next));
  }

  updateHud(msg: HudWsMessage): void {
    const camId = msg.cam_id;
    if (!camId) return;
    const prev = this.data[camId];
    const next: CameraDetection = {
      cam_id: camId,
      has_zone: msg.has_zone,
      person_in_zone: (msg.in_zone_count ?? prev?.in_zone_count ?? 0) > 0,
      in_zone_count: msg.in_zone_count ?? prev?.in_zone_count ?? 0,
      total_persons: prev?.total_persons ?? 0,
      persons: prev?.persons ?? [],
      status: msg.status,
      ui_color: msg.ui_color,
      status_label: msg.status_label,
      sub_label: msg.sub_label,
      polygon_label: msg.polygon_label,
      empty_duration: prev?.empty_duration ?? 0,
      alert_count: msg.alert_count,
      total_alert_seconds: msg.total_alert_seconds,
      session_duration_seconds: msg.session_duration_seconds,
      timeline: msg.timeline ?? prev?.timeline ?? [],
      inference_ms: prev?.inference_ms,
      delay_ms: prev?.delay_ms,
      active_provider: msg.active_provider ?? prev?.active_provider,
      updated_at: prev?.updated_at ?? Date.now() / 1000,
      _client_ts: prev?._client_ts,
    };
    this.data[camId] = next;
    this.hudListeners.get(camId)?.forEach((fn) => fn(next));
  }

  updateAll(nextMap: Record<string, CameraDetection>): void {
    const nowSec = Date.now() / 1000;
    const stamped: Record<string, CameraDetection> = {};
    if (nextMap) {
      for (const [camId, det] of Object.entries(nextMap)) {
        if (det) {
          stamped[camId] = { ...det, _client_ts: nowSec };
        }
      }
    }
    this.data = stamped;
    for (const [camId, listeners] of this.bboxListeners.entries()) {
      const det = this.data[camId] || null;
      listeners.forEach((fn) => fn(det));
    }
    for (const [camId, listeners] of this.hudListeners.entries()) {
      const det = this.data[camId] || null;
      listeners.forEach((fn) => fn(det));
    }
  }

  get(camId: string): CameraDetection | null {
    return this.data[camId] || null;
  }

  subscribeBbox(camId: string, fn: CameraListener): () => void {
    return this._subscribe(this.bboxListeners, camId, fn);
  }

  subscribeHud(camId: string, fn: CameraListener): () => void {
    return this._subscribe(this.hudListeners, camId, fn);
  }

  subscribeCamera(camId: string, fn: CameraListener): () => void {
    return this.subscribeBbox(camId, fn);
  }

  private _subscribe(
    map: Map<string, Set<CameraListener>>,
    camId: string,
    fn: CameraListener,
  ): () => void {
    let set = map.get(camId);
    if (!set) {
      set = new Set();
      map.set(camId, set);
    }
    set.add(fn);
    fn(this.get(camId));
    return () => {
      const current = map.get(camId);
      current?.delete(fn);
      if (current && current.size === 0) {
        map.delete(camId);
      }
    };
  }
}

export const detectionStore = new DetectionStore();
