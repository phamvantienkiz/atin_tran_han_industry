import { api } from '@/lib/api';
import { detectionStore } from '@/lib/detection-store';
import type { CameraDetection } from '@/types';

export function getDetectionsWsUrl(wsPath = '/api/v1/ws/detections'): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const normalizedPath = wsPath.startsWith('/') ? wsPath : `/${wsPath}`;
  return `${proto}//${window.location.host}${normalizedPath}`;
}

export class DetectionsWsClient {
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private focusCamId: string | null = null;
  private closed = false;
  private wsPath = '/api/v1/ws/detections';

  start(wsPath = '/api/v1/ws/detections'): void {
    this.wsPath = wsPath;
    this.closed = false;
    this.connect();
  }

  stop(): void {
    this.closed = true;
    this.stopFallbackPolling();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        // ignore close errors
      }
      this.ws = null;
    }
  }

  setFocus(camId: string | null): void {
    this.focusCamId = camId;
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify({ type: 'focus', cam_id: camId }));
      } catch {
        // fallback REST focus
      }
    }
    api.setDetectionFocus(camId).catch(() => {});
  }

  private connect(): void {
    if (this.closed || typeof window === 'undefined') return;
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    try {
      const url = getDetectionsWsUrl(this.wsPath);
      const socket = new WebSocket(url);
      this.ws = socket;

      socket.onopen = () => {
        this.stopFallbackPolling();
        if (this.focusCamId) {
          try {
            socket.send(JSON.stringify({ type: 'focus', cam_id: this.focusCamId }));
          } catch {
            // ignore
          }
        }
      };

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as {
            type?: string;
            data?: Record<string, CameraDetection>;
          };
          if (msg.type === 'detections' && msg.data) {
            detectionStore.updateAll(msg.data);
          }
        } catch {
          // ignore malformed frames
        }
      };

      socket.onerror = () => {
        this.startFallbackPolling();
      };

      socket.onclose = () => {
        this.ws = null;
        if (!this.closed) {
          this.startFallbackPolling();
          this.scheduleReconnect();
        }
      };
    } catch {
      this.startFallbackPolling();
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.closed || this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, 2000);
  }

  private startFallbackPolling(): void {
    if (this.closed || this.pollTimer) return;
    const runPoll = async () => {
      try {
        const data = await api.detections(this.focusCamId);
        detectionStore.updateAll(data);
      } catch {
        // ignore transient network errors
      }
    };
    void runPoll();
    this.pollTimer = setInterval(() => {
      void runPoll();
    }, 1000);
  }

  private stopFallbackPolling(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }
}

export const detectionsWsClient = new DetectionsWsClient();
