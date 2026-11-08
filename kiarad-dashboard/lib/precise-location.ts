export class LocationAcquisitionError extends Error {
  constructor(public readonly code: number, message: string) { super(message); this.name = "LocationAcquisitionError"; }
}

type Options = { signal?: AbortSignal; timeoutMs?: number; targetAccuracyM?: number };

// Collect real fresh fixes, never average coordinates or manufacture an accuracy value.
export function acquireBestPosition({ signal, timeoutMs = 30_000, targetAccuracyM = 1 }: Options = {}): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      reject(new LocationAcquisitionError(2, "موقعیت‌یاب این دستگاه در دسترس نیست.")); return;
    }
    if (signal?.aborted) { reject(new DOMException("آزمون لغو شد", "AbortError")); return; }
    let watchId: number | undefined, best: GeolocationPosition | undefined, done = false;
    const startedAt = Date.now();
    const waitMs = Math.max(1_000, Math.min(timeoutMs, 60_000));
    const fresh = (position: GeolocationPosition) => Number.isFinite(position.timestamp)
      && position.timestamp >= startedAt - 2_000
      && Date.now() - position.timestamp <= waitMs + 2_000 && position.timestamp - Date.now() <= 5_000;
    const clean = () => {
      if (watchId !== undefined) navigator.geolocation.clearWatch(watchId);
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    };
    const fail = (reason: Error) => { if (!done) { done = true; clean(); reject(reason); } };
    const finish = () => {
      if (done) return;
      if (!best || !fresh(best)) { fail(new LocationAcquisitionError(3, "موقعیت تازه دریافت نشد؛ در فضای باز دوباره تلاش کنید.")); return; }
      done = true; clean(); resolve(best);
    };
    const abort = () => fail(new DOMException("آزمون لغو شد", "AbortError"));
    signal?.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(finish, waitMs);
    try {
      watchId = navigator.geolocation.watchPosition(position => {
        if (done) return;
        const { latitude, longitude, accuracy } = position.coords;
        if (!fresh(position) || !Number.isFinite(latitude) || latitude < -90 || latitude > 90
          || !Number.isFinite(longitude) || longitude < -180 || longitude > 180
          || !Number.isFinite(accuracy) || accuracy <= 0) return;
        if (!best || !fresh(best) || accuracy < best.coords.accuracy) best = position;
        if (best.coords.accuracy <= targetAccuracyM) finish();
      }, error => {
        if (error.code === 1) fail(new LocationAcquisitionError(1, "اجازهٔ موقعیت داده نشده است."));
      }, { enableHighAccuracy: true, maximumAge: 0, timeout: waitMs });
      if (done) navigator.geolocation.clearWatch(watchId);
    } catch {
      fail(new LocationAcquisitionError(2, "دریافت موقعیت ممکن نشد؛ اجازهٔ مرورگر و موقعیت‌یاب را بررسی کنید."));
    }
  });
}
