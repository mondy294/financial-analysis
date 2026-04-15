import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type {
  CollectionFile,
  FundUniverseCacheFile,
  PersistedCompareItem,
  PersistedHoldingItem,
  PersistedScreenerPreset,
  PersistedWatchlistItem,
  ScreenerSectorCacheFile,
} from "./types.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const dataDir = path.resolve(__dirname, "../data");
const watchlistFile = path.join(dataDir, "watchlist.json");
const holdingsFile = path.join(dataDir, "holdings.json");
const compareFile = path.join(dataDir, "compare-list.json");
const fundUniverseFile = path.join(dataDir, "fund-universe-cache.json");
const screenerSectorCacheFile = path.join(dataDir, "screener-sector-cache.json");
const screenerPresetsFile = path.join(dataDir, "screener-presets.json");

async function ensureDataFile<T>(filePath: string, fallback: T) {
  await fs.mkdir(dataDir, { recursive: true });

  try {
    await fs.access(filePath);
  } catch {
    await fs.writeFile(filePath, JSON.stringify(fallback, null, 2), "utf-8");
  }
}

async function readJsonFile<T>(filePath: string, fallback: T): Promise<T> {
  await ensureDataFile(filePath, fallback);
  const raw = await fs.readFile(filePath, "utf-8");

  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

async function writeJsonFile<T>(filePath: string, payload: T) {
  await ensureDataFile(filePath, payload);
  await fs.writeFile(filePath, JSON.stringify(payload, null, 2), "utf-8");
}

async function readCollection<T>(filePath: string): Promise<CollectionFile<T>> {
  const parsed = await readJsonFile<Partial<CollectionFile<T>>>(filePath, { items: [] });
  return {
    items: Array.isArray(parsed.items) ? parsed.items : [],
  };
}

async function writeCollection<T>(filePath: string, items: T[]) {
  await writeJsonFile<CollectionFile<T>>(filePath, { items });
}

export async function getWatchlist() {
  return readCollection<PersistedWatchlistItem>(watchlistFile);
}

export async function saveWatchlist(items: PersistedWatchlistItem[]) {
  await writeCollection<PersistedWatchlistItem>(watchlistFile, items);
}

export async function getHoldings() {
  return readCollection<PersistedHoldingItem>(holdingsFile);
}

export async function saveHoldings(items: PersistedHoldingItem[]) {
  await writeCollection<PersistedHoldingItem>(holdingsFile, items);
}

export async function getCompareList() {
  return readCollection<PersistedCompareItem>(compareFile);
}

export async function saveCompareList(items: PersistedCompareItem[]) {
  await writeCollection<PersistedCompareItem>(compareFile, items);
}

export async function getFundUniverseCache(): Promise<FundUniverseCacheFile> {
  const parsed = await readJsonFile<Partial<FundUniverseCacheFile>>(fundUniverseFile, {
    updatedAt: null,
    coverageNote: "基金池尚未刷新。",
    items: [],
  });

  return {
    updatedAt: typeof parsed.updatedAt === "string" ? parsed.updatedAt : null,
    coverageNote: typeof parsed.coverageNote === "string" ? parsed.coverageNote : "基金池尚未刷新。",
    items: Array.isArray(parsed.items) ? parsed.items : [],
  };
}

export async function saveFundUniverseCache(payload: FundUniverseCacheFile) {
  await writeJsonFile<FundUniverseCacheFile>(fundUniverseFile, payload);
}

export async function getScreenerSectorCache(): Promise<ScreenerSectorCacheFile> {
  const parsed = await readJsonFile<Partial<ScreenerSectorCacheFile>>(screenerSectorCacheFile, {
    updatedAt: null,
    universeUpdatedAt: null,
    coverageNote: "主题板块缓存尚未刷新。",
    items: [],
  });

  return {
    updatedAt: typeof parsed.updatedAt === "string" ? parsed.updatedAt : null,
    universeUpdatedAt: typeof parsed.universeUpdatedAt === "string" ? parsed.universeUpdatedAt : null,
    coverageNote: typeof parsed.coverageNote === "string" ? parsed.coverageNote : "主题板块缓存尚未刷新。",
    items: Array.isArray(parsed.items) ? parsed.items : [],
  };
}

export async function saveScreenerSectorCache(payload: ScreenerSectorCacheFile) {
  await writeJsonFile<ScreenerSectorCacheFile>(screenerSectorCacheFile, payload);
}

export async function getScreenerPresets() {
  return readCollection<PersistedScreenerPreset>(screenerPresetsFile);
}

export async function saveScreenerPresets(items: PersistedScreenerPreset[]) {
  await writeCollection<PersistedScreenerPreset>(screenerPresetsFile, items);
}
