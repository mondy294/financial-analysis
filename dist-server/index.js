import express from "express";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { getHoldings, getWatchlist, saveHoldings, saveWatchlist } from "./data-store.js";
import { getFundPerformance } from "./fund-service.js";
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const distDir = path.resolve(__dirname, "../dist");
const distIndexFile = path.join(distDir, "index.html");
const port = Number(process.env.PORT || 4176);
const app = express();
app.use(express.json());
function toErrorMessage(error) {
    return error instanceof Error ? error.message : "请求失败，请稍后再试。";
}
function validateCode(code) {
    const cleanCode = String(code || "").trim();
    if (!/^\d{6}$/.test(cleanCode)) {
        throw new Error("基金编号必须是 6 位数字。");
    }
    return cleanCode;
}
function parseNullableNumber(value) {
    if (value === null || value === undefined || value === "") {
        return null;
    }
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
}
function normalizeHolding(body) {
    const code = validateCode(String(body.code ?? ""));
    const status = String(body.status ?? "持有中").trim() || "持有中";
    const note = String(body.note ?? "").trim();
    return {
        code,
        status,
        holdingReturnRate: parseNullableNumber(body.holdingReturnRate),
        positionAmount: parseNullableNumber(body.positionAmount),
        costNav: parseNullableNumber(body.costNav),
        note,
        updatedAt: new Date().toISOString(),
    };
}
async function enrichWatchlistItems(items) {
    return Promise.all(items.map(async (item) => {
        try {
            const detail = await getFundPerformance(item.code);
            return { ...item, detail, error: null };
        }
        catch (error) {
            return { ...item, detail: null, error: toErrorMessage(error) };
        }
    }));
}
async function enrichHoldingItems(items) {
    return Promise.all(items.map(async (item) => {
        try {
            const detail = await getFundPerformance(item.code);
            return { ...item, detail, error: null };
        }
        catch (error) {
            return { ...item, detail: null, error: toErrorMessage(error) };
        }
    }));
}
app.get("/api/health", (_request, response) => {
    response.json({ ok: true });
});
app.get("/api/funds/:code", async (request, response) => {
    try {
        const payload = await getFundPerformance(request.params.code);
        response.json(payload);
    }
    catch (error) {
        response.status(500).json({ error: toErrorMessage(error) });
    }
});
app.get("/api/watchlist", async (_request, response) => {
    try {
        const payload = await getWatchlist();
        response.json({ items: await enrichWatchlistItems(payload.items) });
    }
    catch (error) {
        response.status(500).json({ error: toErrorMessage(error) });
    }
});
app.post("/api/watchlist", async (request, response) => {
    try {
        const code = validateCode(String(request.body?.code ?? ""));
        const payload = await getWatchlist();
        if (!payload.items.some((item) => item.code === code)) {
            payload.items.unshift({
                code,
                addedAt: new Date().toISOString(),
            });
            await saveWatchlist(payload.items);
        }
        response.status(201).json({ ok: true });
    }
    catch (error) {
        response.status(400).json({ error: toErrorMessage(error) });
    }
});
app.delete("/api/watchlist/:code", async (request, response) => {
    try {
        const code = validateCode(request.params.code);
        const payload = await getWatchlist();
        const nextItems = payload.items.filter((item) => item.code !== code);
        await saveWatchlist(nextItems);
        response.json({ ok: true });
    }
    catch (error) {
        response.status(400).json({ error: toErrorMessage(error) });
    }
});
app.get("/api/holdings", async (_request, response) => {
    try {
        const payload = await getHoldings();
        response.json({ items: await enrichHoldingItems(payload.items) });
    }
    catch (error) {
        response.status(500).json({ error: toErrorMessage(error) });
    }
});
app.post("/api/holdings", async (request, response) => {
    try {
        const record = normalizeHolding((request.body ?? {}));
        const payload = await getHoldings();
        const nextItems = payload.items.filter((item) => item.code !== record.code);
        nextItems.unshift(record);
        await saveHoldings(nextItems);
        response.status(201).json({ ok: true });
    }
    catch (error) {
        response.status(400).json({ error: toErrorMessage(error) });
    }
});
app.delete("/api/holdings/:code", async (request, response) => {
    try {
        const code = validateCode(request.params.code);
        const payload = await getHoldings();
        const nextItems = payload.items.filter((item) => item.code !== code);
        await saveHoldings(nextItems);
        response.json({ ok: true });
    }
    catch (error) {
        response.status(400).json({ error: toErrorMessage(error) });
    }
});
if (fs.existsSync(distDir)) {
    app.use(express.static(distDir));
}
app.get("*", (_request, response) => {
    if (fs.existsSync(distIndexFile)) {
        response.sendFile(distIndexFile);
        return;
    }
    response.status(200).send("Financial API server is running. Frontend dev server: http://localhost:4177");
});
app.listen(port, () => {
    console.log(`Financial API server is running at http://localhost:${port}`);
});
