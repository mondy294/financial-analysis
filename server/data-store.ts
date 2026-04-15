import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { PersistedHoldingItem, PersistedWatchlistItem } from "./types.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const dataDir = path.resolve(__dirname, "../data");
const watchlistFile = path.join(dataDir, "watchlist.json");
const holdingsFile = path.join(dataDir, "holdings.json");

type CollectionFile<T> = {
  items: T[];
};

async function ensureDataFile<T>(filePath: string, fallback: CollectionFile<T>) {
  await fs.mkdir(dataDir, { recursive: true });

  try {
    await fs.access(filePath);
  } catch {
    await fs.writeFile(filePath, JSON.stringify(fallback, null, 2), "utf-8");
  }
}

async function readCollection<T>(filePath: string): Promise<CollectionFile<T>> {
  const fallback = { items: [] as T[] };
  await ensureDataFile(filePath, fallback);
  const raw = await fs.readFile(filePath, "utf-8");
  const parsed = JSON.parse(raw) as Partial<CollectionFile<T>>;
  return {
    items: Array.isArray(parsed.items) ? parsed.items : [],
  };
}

async function writeCollection<T>(filePath: string, payload: CollectionFile<T>) {
  await ensureDataFile(filePath, payload);
  await fs.writeFile(filePath, JSON.stringify(payload, null, 2), "utf-8");
}

export async function getWatchlist() {
  return readCollection<PersistedWatchlistItem>(watchlistFile);
}

export async function saveWatchlist(items: PersistedWatchlistItem[]) {
  await writeCollection<PersistedWatchlistItem>(watchlistFile, { items });
}

export async function getHoldings() {
  return readCollection<PersistedHoldingItem>(holdingsFile);
}

export async function saveHoldings(items: PersistedHoldingItem[]) {
  await writeCollection<PersistedHoldingItem>(holdingsFile, { items });
}
