// Browser-side Web Push helpers. All calls go to the backend's /api/push/*.

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function swUrl(): string {
  const params = new URLSearchParams({ api: API_BASE });
  if (process.env.NODE_ENV !== "production") params.set("dev", "1");
  return `/sw.js?${params.toString()}`;
}

export function isIos(): boolean {
  if (typeof navigator === "undefined") return false;
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    // iPadOS reports itself as a Mac with touch.
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

export function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

export function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(typeof detail.detail === "string" ? detail.detail : `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export interface PushStatus {
  subscribed: boolean;
  topics: string[];
}

export async function getPushConfig(): Promise<{ enabled: boolean; public_key: string | null }> {
  const res = await fetch(`${API_BASE}/api/push/config`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function getRegistration(): Promise<ServiceWorkerRegistration> {
  const existing = await navigator.serviceWorker.getRegistration("/");
  return existing ?? navigator.serviceWorker.register(swUrl(), { scope: "/" });
}

export async function currentSubscription(): Promise<PushSubscription | null> {
  const reg = await navigator.serviceWorker.getRegistration("/");
  return reg ? reg.pushManager.getSubscription() : null;
}

export function fetchStatus(endpoint: string): Promise<PushStatus> {
  return post("/api/push/status", { endpoint });
}

export async function subscribe(publicKey: string, topics: string[]): Promise<PushStatus> {
  const reg = await getRegistration();
  await navigator.serviceWorker.ready;
  const sub =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey) as BufferSource,
    }));
  return post("/api/push/subscribe", { subscription: sub.toJSON(), topics });
}

export async function unsubscribe(): Promise<void> {
  const sub = await currentSubscription();
  if (!sub) return;
  await post("/api/push/unsubscribe", { endpoint: sub.endpoint }).catch(() => {});
  await sub.unsubscribe();
}

export async function sendTest(): Promise<void> {
  const sub = await currentSubscription();
  if (!sub) throw new Error("Chưa bật thông báo");
  await post("/api/push/test", { endpoint: sub.endpoint });
}
