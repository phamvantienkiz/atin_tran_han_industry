import type { CameraDetection } from '@/types';

type CameraListener = (det: CameraDetection | null) => void;

class DetectionStore {
  private data: Record<string, CameraDetection> = {};
  private camListeners: Map<string, Set<CameraListener>> = new Map();

  updateAll(nextMap: Record<string, CameraDetection>): void {
    this.data = nextMap || {};
    for (const [camId, listeners] of this.camListeners.entries()) {
      const det = this.data[camId] || null;
      listeners.forEach((fn) => fn(det));
    }
  }

  get(camId: string): CameraDetection | null {
    return this.data[camId] || null;
  }

  subscribeCamera(camId: string, fn: CameraListener): () => void {
    let set = this.camListeners.get(camId);
    if (!set) {
      set = new Set();
      this.camListeners.set(camId, set);
    }
    set.add(fn);
    fn(this.get(camId));
    return () => {
      const current = this.camListeners.get(camId);
      current?.delete(fn);
      if (current && current.size === 0) {
        this.camListeners.delete(camId);
      }
    };
  }
}

export const detectionStore = new DetectionStore();
