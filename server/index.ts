import express from "express";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { getCompareList, getHoldings, getWatchlist, saveCompareList, saveHoldings, saveWatchlist } from "./data-store.js";
import { FundAgentService } from "./agent/fund-agent-service.js";
import { getFundPerformance } from "./fund-service.js";
import { startFinancialMcpServer } from "./mcp/index.js";
import {
  deleteScreenerPreset,
  getScreenerOptions,
  getScreenerPresetsList,
  getSectorFunds,
  getSectorStats,
  getUniverseItemByCode,
  queryFundUniverse,
  refreshFundUniverseCache,
  saveScreenerPreset,
} from "./screener-service.js";
import type {
  EnrichedCompareItem,
  EnrichedHoldingItem,
  EnrichedWatchlistItem,
  PersistedCompareItem,
  PersistedHoldingItem,
  PersistedWatchlistItem,
  ScreenerQueryPayload,
} from "./types.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const distDir = path.resolve(__dirname, "../dist");
const distIndexFile = path.join(distDir, "index.html");
const port = Number(process.env.PORT || 3000);

const app = express();
const fundAgentService = new FundAgentService();

app.use(express.json());

function toErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "请求失败，请稍后再试。";
}

function validateCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("基金编号必须是 6 位数字。");
  }
  return cleanCode;
}

function parseNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function normalizeHolding(body: Record<string, unknown>): PersistedHoldingItem {
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

async function enrichWatchlistItems(items: PersistedWatchlistItem[]): Promise<EnrichedWatchlistItem[]> {
  return Promise.all(
    items.map(async (item) => {
      try {
        const detail = await getFundPerformance(item.code);
        return { ...item, detail, error: null };
      } catch (error) {
        return { ...item, detail: null, error: toErrorMessage(error) };
      }
    }),
  );
}

async function enrichHoldingItems(items: PersistedHoldingItem[]): Promise<EnrichedHoldingItem[]> {
  return Promise.all(
    items.map(async (item) => {
      try {
        const detail = await getFundPerformance(item.code);
        return { ...item, detail, error: null };
      } catch (error) {
        return { ...item, detail: null, error: toErrorMessage(error) };
      }
    }),
  );
}

async function enrichCompareItems(items: PersistedCompareItem[]): Promise<EnrichedCompareItem[]> {
  return Promise.all(
    items.map(async (item) => {
      try {
        const [detail, screener] = await Promise.all([getFundPerformance(item.code), getUniverseItemByCode(item.code)]);
        return { ...item, detail, screener, error: null };
      } catch (error) {
        return {
          ...item,
          detail: null,
          screener: await getUniverseItemByCode(item.code),
          error: toErrorMessage(error),
        };
      }
    }),
  );
}

app.get("/api/health", (_request, response) => {
  response.json({ ok: true });
});

app.get("/api/funds/:code", async (request, response) => {
  try {
    const payload = await getFundPerformance(request.params.code);
    response.json(payload);
  } catch (error) {
    response.status(500).json({ error: toErrorMessage(error) });
  }
});

app.post("/api/agent/fund-analysis", async (request, response) => {
  try {
    const fundCode = validateCode(String(request.body?.fundCode ?? ""));
    const horizon = typeof request.body?.horizon === "string" ? request.body.horizon : null;
    const userQuestion = typeof request.body?.userQuestion === "string" ? request.body.userQuestion : null;
    const payload = await fundAgentService.analyzeFund({
      fundCode,
      horizon,
      userQuestion,
    });
    response.json(payload);
  } catch (error) {
    const message = toErrorMessage(error);
    const statusCode = /基金编号必须是 6 位数字/.test(message) ? 400 : 500;
    response.status(statusCode).json({ error: message });
  }
});

app.get("/api/watchlist", async (_request, response) => {
  try {
    const payload = await getWatchlist();
    response.json({ items: await enrichWatchlistItems(payload.items) });
  } catch (error) {
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
  } catch (error) {
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
  } catch (error) {
    response.status(400).json({ error: toErrorMessage(error) });
  }
});

app.get("/api/holdings", async (_request, response) => {
  try {
    const payload = await getHoldings();
    response.json({ items: await enrichHoldingItems(payload.items) });
  } catch (error) {
    response.status(500).json({ error: toErrorMessage(error) });
  }
});

app.post("/api/holdings", async (request, response) => {
  try {
    const record = normalizeHolding((request.body ?? {}) as Record<string, unknown>);
    const payload = await getHoldings();
    const nextItems = payload.items.filter((item) => item.code !== record.code);
    nextItems.unshift(record);
    await saveHoldings(nextItems);
    response.status(201).json({ ok: true });
  } catch (error) {
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
  } catch (error) {
    response.status(400).json({ error: toErrorMessage(error) });
  }
});

app.get("/api/compare", async (_request, response) => {
  try {
    const payload = await getCompareList();
    response.json({ items: await enrichCompareItems(payload.items) });
  } catch (error) {
    response.status(500).json({ error: toErrorMessage(error) });
  }
});

app.post("/api/compare", async (request, response) => {
  try {
    const code = validateCode(String(request.body?.code ?? ""));
    const payload = await getCompareList();

    if (!payload.items.some((item) => item.code === code)) {
      payload.items.unshift({ code, addedAt: new Date().toISOString() });
      await saveCompareList(payload.items.slice(0, 4));
    }

    response.status(201).json({ ok: true });
  } catch (error) {
    response.status(400).json({ error: toErrorMessage(error) });
  }
});

app.delete("/api/compare/:code", async (request, response) => {
  try {
    const code = validateCode(request.params.code);
    const payload = await getCompareList();
    const nextItems = payload.items.filter((item) => item.code !== code);
    await saveCompareList(nextItems);
    response.json({ ok: true });
  } catch (error) {
    response.status(400).json({ error: toErrorMessage(error) });
  }
});

app.get("/api/screener/options", async (_request, response) => {
  try {
    response.json(await getScreenerOptions());
  } catch (error) {
    response.status(500).json({ error: toErrorMessage(error) });
  }
});

app.post("/api/screener/query", async (request, response) => {
  try {
    response.json(await queryFundUniverse((request.body ?? {}) as ScreenerQueryPayload));
  } catch (error) {
    response.status(400).json({ error: toErrorMessage(error) });
  }
});

app.get("/api/screener/sectors", async (_request, response) => {
  try {
    response.json({ items: await getSectorStats() });
  } catch (error) {
    response.status(500).json({ error: toErrorMessage(error) });
  }
});

app.get("/api/screener/sectors/:sector/funds", async (request, response) => {
  try {
    const ranking = typeof request.query.ranking === "string" ? request.query.ranking : null;
    response.json(await getSectorFunds(decodeURIComponent(request.params.sector), ranking as never));
  } catch (error) {
    response.status(500).json({ error: toErrorMessage(error) });
  }
});

app.post("/api/screener/refresh", async (_request, response) => {
  try {
    const cache = await refreshFundUniverseCache();
    response.json({ ok: true, updatedAt: cache.updatedAt, total: cache.items.length, coverageNote: cache.coverageNote });
  } catch (error) {
    response.status(500).json({ error: toErrorMessage(error) });
  }
});

app.get("/api/screener/presets", async (_request, response) => {
  try {
    response.json({ items: await getScreenerPresetsList() });
  } catch (error) {
    response.status(500).json({ error: toErrorMessage(error) });
  }
});

app.post("/api/screener/presets", async (request, response) => {
  try {
    const name = String(request.body?.name ?? "");
    const query = ((request.body?.query ?? {}) as ScreenerQueryPayload);
    response.status(201).json(await saveScreenerPreset(name, query));
  } catch (error) {
    response.status(400).json({ error: toErrorMessage(error) });
  }
});

app.delete("/api/screener/presets/:id", async (request, response) => {
  try {
    await deleteScreenerPreset(String(request.params.id ?? ""));
    response.json({ ok: true });
  } catch (error) {
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

startFinancialMcpServer();
