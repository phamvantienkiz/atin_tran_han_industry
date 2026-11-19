'use client';

interface ToastProps {
  message: string | null;
}

export function Toast({ message }: ToastProps) {
  if (!message) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[60] px-4 py-2.5 rounded-pill bg-brand-ink text-white text-[13px] font-medium shadow-xl border border-white/10 max-w-[90vw] truncate"
    >
      {message}
    </div>
  );
}
