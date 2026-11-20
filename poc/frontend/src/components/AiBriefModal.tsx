'use client';

import { useEffect } from 'react';
import { X } from 'lucide-react';

interface AiBriefModalProps {
  open: boolean;
  onClose: () => void;
}

const BRIEF_ITEMS = [
  {
    color: 'bg-brand-primary',
    title: 'Cam 1 · Kiểm tra đồ bảo hộ lao động',
    desc: 'Phát hiện nhân sự vào khu vực chế biến có mặc đầy đủ trang bị bảo hộ hay không.',
  },
  {
    color: 'bg-status-present',
    title: 'Cam 2 · Giám sát duy trì nhân viên trong vùng máy tăng trọng',
    desc: 'Theo dõi hiện diện nhân viên tại máy tăng trọng (Tăng trọng 1 / 2 / 3): Xanh (Có nhân viên / Vừa rời khỏi vùng 2s) → Vàng (Vùng trống 10s) → Đỏ (Cảnh báo không có nhân viên).',
  },
  {
    color: 'bg-status-empty',
    title: 'Cam 3 · Kiểm tra người trong vùng trực bảo vệ',
    desc: 'Xác định trạng thái có người trực tại chốt / khu vực bảo vệ theo khung giờ quy định.',
  },
  {
    color: 'bg-brand-warm',
    title: 'Cam 4 · Ra/vào kho lạnh, người kẹt & té ngã',
    desc: 'Đếm lượt ra/vào kho lạnh để tính số người còn lại bên trong và phát hiện sự cố té ngã.',
  },
];

export function AiBriefModal({ open, onClose }: AiBriefModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="brief-modal-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 z-50 bg-slate-900/55 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div className="bg-surface-card border border-line rounded-card shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-line-muted flex items-start justify-between gap-3">
          <div>
            <h2 id="brief-modal-title" className="text-[18px] font-semibold text-content-heading">
              Bài toán giám sát AI
            </h2>
            <p className="text-[12px] text-content-secondary mt-0.5">
              Đối chiếu luồng camera thực tế với 4 bài toán giám sát ATIN Smart Fishing
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="icon-btn"
            title="Đóng"
            aria-label="Đóng"
          >
            <X className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>

        <div className="p-6 space-y-3 overflow-y-auto">
          {BRIEF_ITEMS.map((item) => (
            <div
              key={item.title}
              className="flex items-start gap-3 p-3.5 rounded-lg bg-surface-subtle border border-line-muted"
            >
              <span className={`w-2.5 h-2.5 rounded-full mt-1.5 shrink-0 ${item.color}`} />
              <div>
                <div className="text-[14px] font-semibold text-content-heading">{item.title}</div>
                <p className="text-[13px] text-content-secondary mt-1">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
