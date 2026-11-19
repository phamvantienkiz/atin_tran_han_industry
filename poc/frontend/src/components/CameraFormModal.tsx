'use client';

import { useEffect, useState } from 'react';
import { Loader2, Trash2, Upload, X } from 'lucide-react';
import { api } from '@/lib/api';
import { parseZoneJson } from '@/lib/zone-utils';
import type { Camera, StreamMode } from '@/types';

interface CameraFormModalProps {
  open: boolean;
  camera: Camera | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
  onNotify: (msg: string) => void;
}

export function CameraFormModal({
  open,
  camera,
  onClose,
  onSaved,
  onNotify,
}: CameraFormModalProps) {
  const [channel, setChannel] = useState('');
  const [name, setName] = useState('');
  const [zoneName, setZoneName] = useState('');
  const [note, setNote] = useState('');
  const [mode, setMode] = useState<StreamMode>('mjpeg');
  const [subtype, setSubtype] = useState<number>(1);
  const [graceSeconds, setGraceSeconds] = useState('2');
  const [warningSeconds, setWarningSeconds] = useState('10');
  const [zoneJson, setZoneJson] = useState('[]');

  const [formError, setFormError] = useState<string | null>(null);
  const [zoneError, setZoneError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [importingZone, setImportingZone] = useState(false);

  useEffect(() => {
    if (!open) return;
    setFormError(null);
    setZoneError(null);
    if (camera) {
      setChannel(String(camera.channel));
      setName(camera.name);
      setZoneName(camera.zone_name || '');
      setNote(camera.note || '');
      setMode(camera.mode || 'mjpeg');
      setSubtype(camera.subtype ?? 1);
      setGraceSeconds(String(camera.grace_seconds ?? 2));
      setWarningSeconds(String(camera.warning_seconds ?? 10));
      setZoneJson(JSON.stringify(camera.zone || []));
    } else {
      setChannel('');
      setName('');
      setZoneName('');
      setNote('');
      setMode('mjpeg');
      setSubtype(1);
      setGraceSeconds('2');
      setWarningSeconds('10');
      setZoneJson('[]');
    }
  }, [open, camera]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    const chNum = Number(channel);
    const graceNum = Number(graceSeconds);
    const warningNum = Number(warningSeconds);

    if (!Number.isInteger(chNum) || chNum < 1 || chNum > 128) {
      setFormError('Kênh NVR phải là số nguyên từ 1 đến 128');
      return;
    }
    if (!name.trim()) {
      setFormError('Tên hiển thị camera không được để trống');
      return;
    }
    if (Number.isNaN(graceNum) || graceNum < 0 || graceNum > 60) {
      setFormError('Thời gian trễ rời vùng phải từ 0 đến 60 giây');
      return;
    }
    if (Number.isNaN(warningNum) || warningNum < 1 || warningNum > 600) {
      setFormError('Thời gian cảnh báo trống vùng phải từ 1 đến 600 giây');
      return;
    }

    const payload = {
      channel: chNum,
      name: name.trim(),
      zone_name: zoneName.trim(),
      note: note.trim(),
      mode,
      subtype,
      grace_seconds: graceNum,
      warning_seconds: warningNum,
    };

    setSubmitting(true);
    try {
      if (camera) {
        await api.updateCamera(camera.id, payload);
        onNotify(`Đã cập nhật ${payload.name}`);
      } else {
        await api.addCamera(payload);
        onNotify(`Đã thêm ${payload.name}`);
      }
      onClose();
      await onSaved();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Lỗi lưu cấu hình camera';
      setFormError(msg);
      onNotify(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!camera) return;
    setDeleting(true);
    try {
      await api.deleteCamera(camera.id);
      onNotify(`Đã xóa ${camera.name}`);
      onClose();
      await onSaved();
    } catch (err) {
      onNotify(err instanceof Error ? err.message : 'Lỗi xóa camera');
    } finally {
      setDeleting(false);
    }
  };

  const handleImportZone = async () => {
    if (!camera) return;
    setZoneError(null);
    setImportingZone(true);
    try {
      const pts = parseZoneJson(zoneJson.trim());
      if (pts.length < 3) {
        throw new Error('Zone cần tối thiểu 3 điểm');
      }
      await api.saveZone(camera.id, pts);
      onNotify(`Đã import vùng giám sát cho ${camera.name}`);
      onClose();
      await onSaved();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Định dạng Zone JSON không hợp lệ';
      setZoneError(msg);
    } finally {
      setImportingZone(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cam-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 bg-slate-900/55 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div className="bg-surface-card border border-line rounded-card shadow-2xl w-full max-w-lg max-h-[92vh] flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-line-muted flex items-center justify-between gap-3">
          <h2 id="cam-modal-title" className="text-[18px] font-semibold text-content-heading truncate">
            {camera ? `Cài đặt · ${camera.name}` : 'Thêm camera'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="icon-btn"
            title="Đóng hộp thoại"
            aria-label="Đóng hộp thoại"
          >
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4 overflow-y-auto">
          {formError && (
            <div className="px-3.5 py-2.5 rounded-md bg-status-alert/10 border border-status-alert/30 text-[12px] font-medium text-status-alert">
              {formError}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            <label className="block">
              <span className="block text-[12px] font-medium text-content-secondary mb-1.5">
                Kênh NVR (1–128)
              </span>
              <input
                type="number"
                min={1}
                max={128}
                required
                value={channel}
                onChange={(e) => setChannel(e.target.value)}
                placeholder="16"
                className="form-input tabular-nums"
              />
            </label>

            <label className="block">
              <span className="block text-[12px] font-medium text-content-secondary mb-1.5">
                Tên hiển thị
              </span>
              <input
                type="text"
                required
                maxLength={120}
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Tăng trọng 1"
                className="form-input"
              />
            </label>
          </div>

          <label className="block">
            <span className="block text-[12px] font-medium text-content-secondary mb-1.5">
              Tên vùng trên HUD
            </span>
            <input
              type="text"
              maxLength={120}
              value={zoneName}
              onChange={(e) => setZoneName(e.target.value)}
              placeholder="Ví dụ: Vùng máy trộn (mặc định dùng tên camera)"
              className="form-input"
            />
          </label>

          <label className="block">
            <span className="block text-[12px] font-medium text-content-secondary mb-1.5">
              Ghi chú / Bài toán
            </span>
            <input
              type="text"
              maxLength={240}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Ví dụ: Khu vực máy tăng trọng 1"
              className="form-input"
            />
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            <label className="block">
              <span className="block text-[12px] font-medium text-content-secondary mb-1.5">
                Chế độ phát
              </span>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as StreamMode)}
                className="form-input"
              >
                <option value="mjpeg">MJPEG trực tiếp</option>
                <option value="snapshot">Snapshot định kỳ (1.5s)</option>
              </select>
            </label>

            <label className="block">
              <span className="block text-[12px] font-medium text-content-secondary mb-1.5">
                Luồng NVR
              </span>
              <select
                value={subtype}
                onChange={(e) => setSubtype(Number(e.target.value))}
                className="form-input"
              >
                <option value={0}>Luồng chính (Main-stream)</option>
                <option value={1}>Luồng phụ (Sub-stream)</option>
              </select>
            </label>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            <label className="block">
              <span className="block text-[12px] font-medium text-content-secondary mb-1.5">
                Trễ rời vùng (giây)
              </span>
              <input
                type="number"
                step="0.5"
                min={0}
                max={60}
                value={graceSeconds}
                onChange={(e) => setGraceSeconds(e.target.value)}
                className="form-input tabular-nums"
              />
            </label>

            <label className="block">
              <span className="block text-[12px] font-medium text-content-secondary mb-1.5">
                Ngưỡng báo đỏ (giây)
              </span>
              <input
                type="number"
                step="1"
                min={1}
                max={600}
                value={warningSeconds}
                onChange={(e) => setWarningSeconds(e.target.value)}
                className="form-input tabular-nums"
              />
            </label>
          </div>

          {camera && (
            <div className="pt-3 border-t border-line-muted space-y-2.5">
              <label className="block">
                <span className="block text-[12px] font-medium text-content-secondary mb-1.5">
                  Zone JSON (tọa độ chuẩn hóa 0–1)
                </span>
                <textarea
                  rows={3}
                  value={zoneJson}
                  onChange={(e) => {
                    setZoneJson(e.target.value);
                    setZoneError(null);
                  }}
                  placeholder='[{"x":0.1,"y":0.35},...]'
                  className={`w-full p-3 rounded-md border bg-surface-subtle text-[13px] font-mono text-content-heading focus:bg-surface-card focus:border-brand-primary focus:outline-none ${
                    zoneError ? 'form-input-error' : 'border-line'
                  }`}
                />
                {zoneError && (
                  <p className="text-[12px] text-status-alert mt-1">{zoneError}</p>
                )}
              </label>

              <button
                type="button"
                onClick={handleImportZone}
                disabled={importingZone}
                className="btn-subtle w-full"
              >
                {importingZone ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Upload className="w-4 h-4" strokeWidth={1.5} />
                )}
                <span>{importingZone ? 'Đang lưu...' : 'Import tọa độ Zone'}</span>
              </button>
            </div>
          )}

          <div className="pt-4 border-t border-line-muted flex items-center gap-2">
            {camera && (
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting || submitting}
                className="btn-danger"
              >
                {deleting ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" strokeWidth={1.5} />
                )}
                <span>{deleting ? 'Đang xóa...' : 'Xóa camera'}</span>
              </button>
            )}
            <div className="flex-1" />
            <button
              type="button"
              onClick={onClose}
              disabled={submitting || deleting}
              className="btn-subtle"
            >
              Hủy
            </button>
            <button
              type="submit"
              disabled={submitting || deleting}
              className="btn-primary"
            >
              {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
              <span>{submitting ? 'Đang lưu...' : 'Lưu thay đổi'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
