/** 浏览器本地个股备注（无登录；仅本机）。 */

const KEY = "qs-stock-notes";

export type StockNote = {
  text: string;
  updated_at: string;
};

function normalizeCode(code: string): string {
  return code.trim().toUpperCase();
}

function readAll(): Record<string, StockNote> {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out: Record<string, StockNote> = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      const code = normalizeCode(k);
      if (!code || !v || typeof v !== "object") continue;
      const text = String((v as StockNote).text || "").trim();
      if (!text) continue;
      const updated =
        typeof (v as StockNote).updated_at === "string"
          ? (v as StockNote).updated_at
          : new Date().toISOString();
      out[code] = { text, updated_at: updated };
    }
    return out;
  } catch {
    return {};
  }
}

function writeAll(map: Record<string, StockNote>): void {
  localStorage.setItem(KEY, JSON.stringify(map));
  window.dispatchEvent(new CustomEvent("qs-stock-notes-changed"));
}

export function getStockNote(code: string): StockNote | null {
  const c = normalizeCode(code);
  if (!c) return null;
  return readAll()[c] || null;
}

export function setStockNote(code: string, text: string): StockNote | null {
  const c = normalizeCode(code);
  if (!c) return null;
  const map = readAll();
  const trimmed = text.trim();
  if (!trimmed) {
    delete map[c];
    writeAll(map);
    return null;
  }
  const note: StockNote = { text: trimmed, updated_at: new Date().toISOString() };
  map[c] = note;
  writeAll(map);
  return note;
}

export function clearStockNote(code: string): void {
  setStockNote(code, "");
}

export function subscribeStockNotes(cb: () => void): () => void {
  const onCustom = () => cb();
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY || e.key === null) cb();
  };
  window.addEventListener("qs-stock-notes-changed", onCustom);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener("qs-stock-notes-changed", onCustom);
    window.removeEventListener("storage", onStorage);
  };
}
