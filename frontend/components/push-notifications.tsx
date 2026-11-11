"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, BellRing, Loader2 } from "lucide-react";

import { IosInstallGuide } from "@/components/ios-install-guide";
import {
  currentSubscription,
  fetchStatus,
  getPushConfig,
  isIos,
  isStandalone,
  pushSupported,
  sendTest,
  subscribe,
  unsubscribe,
} from "@/lib/push";
import type { Category } from "@/lib/types";
import { headerIconButton } from "@/lib/ui";
import { cn } from "@/lib/utils";

type Availability = "loading" | "unsupported" | "needs-install" | "server-off" | "unreachable" | "denied" | "ready";

export function PushNotifications({ categories }: { categories: Category[] }) {
  const [open, setOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [availability, setAvailability] = useState<Availability>("loading");
  const [publicKey, setPublicKey] = useState<string | null>(null);
  const [subscribed, setSubscribed] = useState(false);
  // Empty = every topic.
  const [topics, setTopics] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    if (!pushSupported()) {
      setAvailability(isIos() && !isStandalone() ? "needs-install" : "unsupported");
      return;
    }
    if (isIos() && !isStandalone()) {
      setAvailability("needs-install");
      return;
    }
    try {
      const config = await getPushConfig();
      if (!config.enabled || !config.public_key) {
        setAvailability("server-off");
        return;
      }
      setPublicKey(config.public_key);
    } catch {
      setAvailability("unreachable");
      return;
    }
    if (Notification.permission === "denied") {
      setAvailability("denied");
      return;
    }
    setAvailability("ready");
    const sub = await currentSubscription().catch(() => null);
    if (!sub) {
      setSubscribed(false);
      return;
    }
    const status = await fetchStatus(sub.endpoint).catch(() => null);
    setSubscribed(Boolean(status?.subscribed));
    setTopics(status?.topics ?? []);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Close the panel on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    setMessage(null);
    try {
      await action();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Có lỗi xảy ra");
    } finally {
      setBusy(false);
    }
  };

  const enable = () =>
    run(async () => {
      // Must be called from the click itself (iOS requires a user gesture).
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setAvailability(permission === "denied" ? "denied" : "ready");
        throw new Error("Bạn chưa cho phép thông báo.");
      }
      const status = await subscribe(publicKey!, topics);
      setSubscribed(status.subscribed);
      setTopics(status.topics);
      setMessage("Đã bật thông báo.");
    });

  const save = () =>
    run(async () => {
      const status = await subscribe(publicKey!, topics);
      setTopics(status.topics);
      setMessage("Đã lưu chuyên mục.");
    });

  const disable = () =>
    run(async () => {
      await unsubscribe();
      setSubscribed(false);
      setMessage("Đã tắt thông báo.");
    });

  const test = () =>
    run(async () => {
      await sendTest();
      setMessage("Đã gửi thông báo thử.");
    });

  const toggleTopic = (slug: string) =>
    setTopics((prev) => (prev.includes(slug) ? prev.filter((t) => t !== slug) : [...prev, slug]));

  const Icon = subscribed ? BellRing : Bell;

  return (
    <div className="relative" ref={panelRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(headerIconButton, subscribed && "text-primary hover:text-primary")}
        aria-label="Thông báo"
        title="Thông báo"
        aria-expanded={open}
      >
        <Icon className="h-4 w-4" />
        {subscribed && <span className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-primary" />}
      </button>

      {open && (
        // Positioning lives on this wrapper: .glass-card sets position: relative
        // outside Tailwind's layers and would override `absolute`.
        <div className="absolute right-0 top-10 z-40 w-[min(20rem,calc(100vw-2rem))]">
          <div className="glass-card space-y-3 rounded-2xl bg-background/95 p-4 shadow-xl">
            <div>
              <div className="text-sm font-bold">Thông báo tin nóng</div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Nhận thông báo khi có tin quan trọng, tối đa vài tin mỗi giờ.
              </p>
            </div>

            {availability === "loading" && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
            {availability === "unsupported" && (
              <p className="text-sm text-muted-foreground">Trình duyệt này không hỗ trợ thông báo đẩy.</p>
            )}
            {availability === "server-off" && (
              <p className="text-sm text-muted-foreground">Máy chủ chưa bật thông báo đẩy.</p>
            )}
            {availability === "unreachable" && (
              <p className="text-sm text-muted-foreground">Không kết nối được máy chủ. Hãy thử lại sau.</p>
            )}
            {availability === "denied" && (
              <p className="text-sm text-muted-foreground">
                Bạn đã chặn thông báo cho trang này. Hãy cho phép lại trong cài đặt trình duyệt.
              </p>
            )}
            {availability === "needs-install" && (
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">
                  Trên iPhone/iPad, cần cài Tech Digest vào Màn hình chính trước khi bật thông báo.
                </p>
                <button
                  type="button"
                  onClick={() => setGuideOpen(true)}
                  className="w-full rounded-xl bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground"
                >
                  Xem hướng dẫn cài
                </button>
              </div>
            )}

            {availability === "ready" && (
              <>
                <div>
                  <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Chuyên mục
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <TopicChip label="Tất cả" active={topics.length === 0} onClick={() => setTopics([])} />
                    {categories.map((c) => (
                      <TopicChip
                        key={c.slug}
                        label={c.name}
                        active={topics.includes(c.slug)}
                        onClick={() => toggleTopic(c.slug)}
                      />
                    ))}
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {subscribed ? (
                    <>
                      <ActionButton onClick={save} disabled={busy} primary>
                        Lưu
                      </ActionButton>
                      <ActionButton onClick={test} disabled={busy}>
                        Gửi thử
                      </ActionButton>
                      <ActionButton onClick={disable} disabled={busy}>
                        Tắt
                      </ActionButton>
                    </>
                  ) : (
                    <ActionButton onClick={enable} disabled={busy} primary>
                      {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      Bật thông báo
                    </ActionButton>
                  )}
                </div>
              </>
            )}

            {message && (
              <p role="status" className="text-xs text-muted-foreground">
                {message}
              </p>
            )}
          </div>
        </div>
      )}

      <IosInstallGuide open={guideOpen} onClose={() => setGuideOpen(false)} />
    </div>
  );
}

function TopicChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "rounded-full border px-2.5 py-1 text-xs font-medium transition",
        active
          ? "border-transparent bg-primary text-primary-foreground"
          : "border-border text-muted-foreground hover:border-primary/40 hover:text-foreground"
      )}
    >
      {label}
    </button>
  );
}

function ActionButton({
  children,
  onClick,
  disabled,
  primary,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-sm font-semibold transition disabled:opacity-60",
        primary ? "bg-primary text-primary-foreground hover:opacity-90" : "border border-border/60 hover:bg-muted"
      )}
    >
      {children}
    </button>
  );
}
