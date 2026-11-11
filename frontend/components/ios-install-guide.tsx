"use client";

import { useEffect } from "react";
import { Share, SquarePlus, Smartphone, X } from "lucide-react";

/** iOS has no automatic install prompt, and Web Push only works once the
 *  app is installed to the Home Screen — so we explain the 3 steps. */
export function IosInstallGuide({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const steps = [
    { icon: Share, text: "Mở trang này bằng Safari rồi nhấn nút Chia sẻ ở thanh công cụ." },
    { icon: SquarePlus, text: "Kéo xuống và chọn “Thêm vào MH chính” (Add to Home Screen)." },
    { icon: Smartphone, text: "Mở Tech Digest từ biểu tượng mới trên màn hình chính, rồi bật thông báo." },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 backdrop-blur-sm sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="ios-install-title"
      onClick={onClose}
    >
      <div
        className="glass-card w-full max-w-sm rounded-2xl bg-background p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h2 id="ios-install-title" className="text-base font-bold">
            Cài Tech Digest trên iPhone / iPad
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-muted-foreground hover:bg-muted"
            aria-label="Đóng"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <ol className="space-y-3">
          {steps.map(({ icon: Icon, text }, i) => (
            <li key={i} className="flex items-start gap-3 text-sm">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <Icon className="h-4 w-4" />
              </span>
              <span className="pt-1.5">{text}</span>
            </li>
          ))}
        </ol>
        <p className="mt-4 text-xs text-muted-foreground">
          Trên iOS, thông báo đẩy chỉ hoạt động khi mở app từ Màn hình chính (iOS 16.4 trở lên).
        </p>
      </div>
    </div>
  );
}
