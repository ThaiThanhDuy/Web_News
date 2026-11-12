"use client";

import { useEffect, useState } from "react";
import { Download, WifiOff } from "lucide-react";

import { IosInstallGuide } from "@/components/ios-install-guide";
import { isIos, isStandalone, swUrl } from "@/lib/push";
import { headerIconButton } from "@/lib/ui";

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

/** Registers the service worker. In dev it runs in push-only mode
 *  (?dev=1: no caching), so notifications can be tested with `npm run dev`. */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const register = () => navigator.serviceWorker.register(swUrl(), { scope: "/" }).catch(() => {});
    if (document.readyState === "complete") register();
    else window.addEventListener("load", register, { once: true });
  }, []);

  return null;
}

/** "Cài ứng dụng" button: the browser's own prompt where available
 *  (Chrome/Edge/Android), or a how-to guide on iOS, which has none. */
export function InstallButton() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [iosGuide, setIosGuide] = useState(false);
  const [showIos, setShowIos] = useState(false);

  useEffect(() => {
    setShowIos(isIos() && !isStandalone());
    const onPrompt = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
    };
    const onInstalled = () => setDeferred(null);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (!deferred && !showIos) return null;

  return (
    <>
      <button
        type="button"
        onClick={async () => {
          if (!deferred) {
            setIosGuide(true);
            return;
          }
          await deferred.prompt();
          await deferred.userChoice;
          setDeferred(null);
        }}
        className={headerIconButton}
        aria-label="Cài ứng dụng"
        title="Cài ứng dụng"
      >
        <Download className="h-4 w-4" />
      </button>
      <IosInstallGuide open={iosGuide} onClose={() => setIosGuide(false)} />
    </>
  );
}

/** Small banner shown while the device is offline. */
export function OfflineIndicator() {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    const update = () => setOffline(!navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  if (!offline) return null;

  return (
    <div
      role="status"
      className="fixed bottom-[calc(1rem+env(safe-area-inset-bottom))] left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full bg-foreground px-4 py-2 text-sm font-medium text-background shadow-lg"
    >
      <WifiOff className="h-4 w-4" />
      Đang ngoại tuyến — hiển thị nội dung đã lưu
    </div>
  );
}
