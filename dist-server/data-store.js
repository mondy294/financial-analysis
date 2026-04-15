import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const dataDir = path.resolve(__dirname, "../data");
const watchlistFile = path.join(dataDir, "watchlist.json");
const holdingsFile = path.join(dataDir, "holdings.json");
async function ensureDataFile(filePath, fallback) {
    await fs.mkdir(dataDir, { recursive: true });
    try {
        await fs.access(filePath);
    }
    catch {
        await fs.writeFile(filePath, JSON.stringify(fallback, null, 2), "utf-8");
    }
}
async function readCollection(filePath) {
    const fallback = { items: [] };
    await ensureDataFile(filePath, fallback);
    const raw = await fs.readFile(filePath, "utf-8");
    const parsed = JSON.parse(raw);
    return {
        items: Array.isArray(parsed.items) ? parsed.items : [],
    };
}
async function writeCollection(filePath, payload) {
    await ensureDataFile(filePath, payload);
    await fs.writeFile(filePath, JSON.stringify(payload, null, 2), "utf-8");
}
export async function getWatchlist() {
    return readCollection(watchlistFile);
}
export async function saveWatchlist(items) {
    await writeCollection(watchlistFile, { items });
}
export async function getHoldings() {
    return readCollection(holdingsFile);
}
export async function saveHoldings(items) {
    await writeCollection(holdingsFile, { items });
}
