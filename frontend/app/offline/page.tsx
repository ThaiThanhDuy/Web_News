import type { Metadata } from "next";
import { WifiOff } from "lucide-react";

import { RetryButton } from "./retry-button";

export const metadata: Metadata = {
  title: "Mất kết nối — Tech Digest",
};

export const dynamic = "force-static";

export default function OfflinePage() {
  return (
    <div className="glass-card mx-auto mt-10 flex max-w-md flex-col items-center gap-4 rounded-2xl p-8 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <WifiOff className="h-7 w-7" />
      </span>
      <h1 className="text-xl font-bold">Bạn đang ngoại tuyến</h1>
      <p className="text-sm text-muted-foreground">
        Trang này chưa được lưu để đọc offline. Những trang bạn đã mở trước đó vẫn xem được — hãy thử
        lại khi có mạng.
      </p>
      <RetryButton />
    </div>
  );
}
