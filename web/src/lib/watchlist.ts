/** 浏览器本地自选股（无登录；仅本机）。 */

const KEY = "qs-watchlist";

export type WatchlistItem = {
  code: string;
  /** 加入时缓存的名称，便于列表展示 */
  name?: string;
  added_at: string;
};

function normalizeCode(code: string): string {
  return code.trim().toUpperCase();
}

function readRaw(): WatchlistItem[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    const out: WatchlistItem[] = [];
    const seen = new Set<string>();
    for (const row of parsed) {
      if (!row || typeof row !== "object") continue;
      const code = normalizeCode(String((row as WatchlistItem).code || ""));
      if (!code || seen.has(code)) continue;
      seen.add(code);
      const name = (row as WatchlistItem).name;
      const added =
        typeof (row as WatchlistItem).added_at === "string"
          ? (row as WatchlistItem).added_at
          : new Date().toISOString();
      out.push({
        code,
        name: typeof name === "string" && name.trim() ? name.trim() : undefined,
        added_at: added,
      });
    }
    return out;
  } catch {
    return [];
  }
}

function writeRaw(items: WatchlistItem[]): void {
  localStorage.setItem(KEY, JSON.stringify(items));
  window.dispatchEvent(new CustomEvent("qs-watchlist-changed"));
}

export function listWatchlist(): WatchlistItem[] {
  return readRaw();
}

export function isWatched(code: string): boolean {
  const c = normalizeCode(code);
  if (!c) return false;
  return readRaw().some((x) => x.code === c);
}

export function addWatch(code: string, name?: string): WatchlistItem[] {
  const c = normalizeCode(code);
  if (!c) return readRaw();
  const cur = readRaw();
  if (cur.some((x) => x.code === c)) {
    if (name?.trim()) {
      const next = cur.map((x) =>
        x.code === c ? { ...x, name: name.trim() } : x,
      );
      writeRaw(next);
      return next;
    }
    return cur;
  }
  const next = [
    {
      code: c,
      name: name?.trim() || undefined,
      added_at: new Date().toISOString(),
    },
    ...cur,
  ];
  writeRaw(next);
  return next;
}

export function removeWatch(code: string): WatchlistItem[] {
  const c = normalizeCode(code);
  const next = readRaw().filter((x) => x.code !== c);
  writeRaw(next);
  return next;
}

export function toggleWatch(code: string, name?: string): boolean {
  if (isWatched(code)) {
    removeWatch(code);
    return false;
  }
  addWatch(code, name);
  return true;
}

/** 订阅自选变更（同页多组件 / 跨标签页 storage 事件） */
export function subscribeWatchlist(cb: () => void): () => void {
  const onCustom = () => cb();
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY || e.key === null) cb();
  };
  window.addEventListener("qs-watchlist-changed", onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener("qs-watchlist-changed", onCustom);
    window.removeEventListener("storage", onStorage);
  };
}
