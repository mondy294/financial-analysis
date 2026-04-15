import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const dataDir = path.resolve(__dirname, "../data");
const watchlistFile = path.join(dataDir, "watchlist.json");
const holdingsFile = path.join(dataDir, "holdings.json");
const compareFile = path.join(dataDir, "compare-list.json");
const fundUniverseFile = path.join(dataDir, "fund-universe-cache.json");
const screenerPresetsFile = path.join(dataDir, "screener-presets.json");
async function ensureDataFile(filePath, fallback) {
    await fs.mkdir(dataDir, { recursive: true });
    try {
        await fs.access(filePath);
    }
    catch {
        await fs.writeFile(filePath, JSON.stringify(fallback, null, 2), "utf-8");
    }
}
async function readJsonFile(filePath, fallback) {
    await ensureDataFile(filePath, fallback);
    const raw = await fs.readFile(filePath, "utf-8");
    try {
        return JSON.parse(raw);
    }
    catch {
        return fallback;
    }
}
async function writeJsonFile(filePath, payload) {
    await ensureDataFile(filePath, payload);
    await fs.writeFile(filePath, JSON.stringify(payload, null, 2), "utf-8");
}
async function readCollection(filePath) {
    const parsed = await readJsonFile(filePath, { items: [] });
    return {
        items: Array.isArray(parsed.items) ? parsed.items : [],
    };
}
async function writeCollection(filePath, items) {
    await writeJsonFile(filePath, { items });
}
export async function getWatchlist() {
    return readCollection(watchlistFile);
}
export async function saveWatchlist(items) {
    await writeCollection(watchlistFile, items);
}
export async function getHoldings() {
    return readCollection(holdingsFile);
}
export async function saveHoldings(items) {
    await writeCollection(holdingsFile, items);
}
export async function getCompareList() {
    return readCollection(compareFile);
}
export async function saveCompareList(items) {
    await writeCollection(compareFile, items);
}
export async function getFundUniverseCache() {
    const parsed = await readJsonFile(fundUniverseFile, {
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
export async function saveFundUniverseCache(payload) {
    await writeJsonFile(fundUniverseFile, payload);
}
export async function getScreenerPresets() {
    return readCollection(screenerPresetsFile);
}
export async function saveScreenerPresets(items) {
    await writeCollection(screenerPresetsFile, items);
}
