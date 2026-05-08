import type {
  FundHoldingStock,
  FundHoldingStocksLookupResponse,
  StockDetailResponse,
  StockKLinePoint,
  StockMeta,
  StockPerformanceSummary,
  StockQuoteSnapshot,
} from "./types.js";

type RawHoldingQuoteItem = {
  f12?: string;
  f14?: string;
  f2?: number | string;
  f3?: number | string;
  f4?: number | string;
  f17?: number | string;
  f15?: number | string;
  f16?: number | string;
  f18?: number | string;
  f5?: number | string;
  f6?: number | string;
};

type RawHoldingQuoteResponse = {
  data?: {
    diff?: RawHoldingQuoteItem[];
  };
};

type RawKLineResponse = {
  data?: {
    code?: string;
    name?: string;
    market?: number;
    klines?: string[];
  };
};

type ParsedHoldingRow = FundHoldingStock & {
  secId: string;
};

type StockQuoteInput = {
  code: string;
  exchange?: string | null;
  secId?: string | null;
};

const USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36";

const API_HEADERS = {
  "user-agent": USER_AGENT,
  accept: "application/json, text/plain, */*",
};

function parseNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function parseLooseNumber(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }

  return parseNumber(value.replace(/,/g, "").replace(/%/g, "").trim());
}

function normalizeFundCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error("基金编号必须是 6 位数字。");
  }
  return cleanCode;
}

function normalizeStockCode(code: string) {
  const cleanCode = String(code || "").trim();
  if (!/^\d{6}$/.test(cleanCode)) {
    throw new Error(`股票代码格式不正确：${code}`);
  }
  return cleanCode;
}

function normalizeExchange(exchange?: string | null) {
  const upper = String(exchange || "").trim().toUpperCase();
  if (!upper) {
    return null;
  }

  if (["SH", "SZ", "BJ"].includes(upper)) {
    return upper as "SH" | "SZ" | "BJ";
  }

  throw new Error(`暂不支持的交易所标识：${exchange}`);
}

function inferExchangeFromCode(code: string) {
  if (/^(4|8|92)/.test(code)) {
    return "BJ";
  }

  if (/^(5|6|9)/.test(code)) {
    return "SH";
  }

  return "SZ";
}

function inferExchange(code: string, secId: string) {
  if (secId.startsWith("1.")) {
    return "SH";
  }

  if (/^(4|8|92)/.test(code)) {
    return "BJ";
  }

  return "SZ";
}

function toSecId(code: string, exchange?: string | null, secId?: string | null) {
  const cleanCode = normalizeStockCode(code);
  const cleanSecId = String(secId || "").trim();
  if (/^[01]\.\d{6}$/.test(cleanSecId)) {
    return cleanSecId;
  }

  const targetExchange = normalizeExchange(exchange) ?? inferExchangeFromCode(cleanCode);
  return `${targetExchange === "SH" ? "1" : "0"}.${cleanCode}`;
}

function buildPricePerformanceSummary(kline: StockKLinePoint[]): StockPerformanceSummary {
  const closes = kline.filter((item): item is StockKLinePoint & { close: number } => typeof item.close === "number" && Number.isFinite(item.close));
  const latestDate = closes.at(-1)?.date ?? new Date().toISOString().slice(0, 10);
  const ytdStart = `${latestDate.slice(0, 4)}-01-01`;

  function tradingDayReturn(periodsBack: number) {
    if (closes.length <= periodsBack) {
      return null;
    }
    const latest = closes.at(-1)?.close;
    const base = closes.at(-(periodsBack + 1))?.close;
    if (typeof latest !== "number" || typeof base !== "number" || base === 0) {
      return null;
    }
    return Number((((latest - base) / base) * 100).toFixed(2));
  }

  function rangeReturn(items: Array<StockKLinePoint & { close: number }>) {
    const first = items[0]?.close;
    const last = items.at(-1)?.close;
    if (typeof first !== "number" || typeof last !== "number" || first === 0) {
      return null;
    }
    return Number((((last - first) / first) * 100).toFixed(2));
  }

  const ytdItems = closes.filter((item) => item.date >= ytdStart);
  const recent30 = closes.slice(-30).map((item) => item.close);

  return {
    oneWeek: tradingDayReturn(5),
    oneMonth: tradingDayReturn(20),
    threeMonths: tradingDayReturn(60),
    sixMonths: tradingDayReturn(120),
    oneYear: tradingDayReturn(250),
    yearToDate: ytdItems.length >= 2 ? rangeReturn(ytdItems) : null,
    sinceInception: closes.length >= 2 ? rangeReturn(closes) : null,
    lowestRecentClose: recent30.length > 0 ? Math.min(...recent30) : null,
    highestRecentClose: recent30.length > 0 ? Math.max(...recent30) : null,
  };
}

function parseKLinePoint(line: string): StockKLinePoint | null {
  const parts = line.split(",");
  if (parts.length < 11) {
    return null;
  }

  return {
    date: parts[0] ?? "",
    open: parseLooseNumber(parts[1]),
    close: parseLooseNumber(parts[2]),
    high: parseLooseNumber(parts[3]),
    low: parseLooseNumber(parts[4]),
    volume: parseLooseNumber(parts[5]),
    amount: parseLooseNumber(parts[6]),
    amplitude: parseLooseNumber(parts[7]),
    changeRate: parseLooseNumber(parts[8]),
    changeAmount: parseLooseNumber(parts[9]),
    turnoverRate: parseLooseNumber(parts[10]),
  };
}

async function fetchText(url: string, init?: RequestInit): Promise<string> {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...API_HEADERS,
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }

  return response.text();
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...API_HEADERS,
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }

  return response.json() as Promise<T>;
}

function parseLatestFundHoldings(source: string): { reportDate: string | null; items: ParsedHoldingRow[] } {
  const contentMatch = source.match(/content:"([\s\S]*?)",arryear:/);
  const content = contentMatch?.[1]
    ?.replace(/\\r/g, "")
    .replace(/\\n/g, "")
    .replace(/\\\//g, "/")
    .replace(/\\"/g, '"') ?? "";

  if (!content) {
    return { reportDate: null, items: [] };
  }

  const reportDate = content.match(/截止至：<font class='px12'>([^<]+)<\/font>/)?.[1] ?? null;
  const bodyMatch = content.match(/<table class='w782 comm tzxq'>[\s\S]*?<tbody>([\s\S]*?)<\/tbody>/);

  if (!bodyMatch?.[1]) {
    return { reportDate, items: [] };
  }

  const rowMatches = bodyMatch[1].matchAll(/<tr><td>\d+<\/td><td><a href='\/\/quote\.eastmoney\.com\/unify\/r\/([^']+)'>(\d{6})<\/a><\/td><td class='tol'><a [^>]*>([^<]+)<\/a><\/td><td class='tor'><span[^>]*><\/span><\/td><td class='tor'><span[^>]*><\/span><\/td><td class='xglj'>[\s\S]*?<\/td><td class='tor'>([^<]*)<\/td><td class='tor'>([^<]*)<\/td><td class='tor'>([^<]*)<\/td><\/tr>/g);

  const items = Array.from(rowMatches, (match) => {
    const secId = match[1];
    const code = match[2];

    return {
      secId,
      code,
      name: match[3].trim(),
      exchange: inferExchange(code, secId),
      latestPrice: null,
      changeRate: null,
      changeAmount: null,
      navRatio: parseLooseNumber(match[4]),
      holdingSharesWan: parseLooseNumber(match[5]),
      holdingMarketValueWan: parseLooseNumber(match[6]),
    } satisfies ParsedHoldingRow;
  });

  return {
    reportDate,
    items,
  };
}

export async function getRealtimeStockQuotes(stocks: StockQuoteInput[]): Promise<StockQuoteSnapshot[]> {
  if (stocks.length === 0) {
    return [];
  }

  const normalized = stocks.map((item) => {
    const code = normalizeStockCode(item.code);
    const exchange = normalizeExchange(item.exchange) ?? inferExchangeFromCode(code);
    return {
      code,
      exchange,
      secId: toSecId(code, exchange, item.secId),
    };
  });

  const deduped = [...new Map(normalized.map((item) => [`${item.secId}:${item.code}`, item])).values()];
  const secids = deduped.map((item) => item.secId).join(",");
  const quoteUrl = `https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&invt=2&fields=f12,f14,f2,f3,f4,f17,f15,f16,f18,f5,f6&secids=${encodeURIComponent(secids)}`;
  const quotePayload = await fetchJson<RawHoldingQuoteResponse>(quoteUrl, {
    headers: {
      referer: "https://quote.eastmoney.com/",
    },
  });

  const quoteMap = new Map(
    (quotePayload.data?.diff ?? [])
      .filter((item): item is RawHoldingQuoteItem & { f12: string } => Boolean(item.f12))
      .map((item) => [
        item.f12,
        {
          name: item.f14?.trim() || null,
          latestPrice: parseNumber(item.f2),
          changeRate: parseNumber(item.f3),
          changeAmount: parseNumber(item.f4),
          openPrice: parseNumber(item.f17),
          highPrice: parseNumber(item.f15),
          lowPrice: parseNumber(item.f16),
          previousClose: parseNumber(item.f18),
          volume: parseNumber(item.f5),
          amount: parseNumber(item.f6),
        },
      ]),
  );

  return deduped.map((item) => {
    const quote = quoteMap.get(item.code);
    return {
      code: item.code,
      name: quote?.name ?? null,
      exchange: item.exchange,
      secId: item.secId,
      latestPrice: quote?.latestPrice ?? null,
      changeRate: quote?.changeRate ?? null,
      changeAmount: quote?.changeAmount ?? null,
      openPrice: quote?.openPrice ?? null,
      highPrice: quote?.highPrice ?? null,
      lowPrice: quote?.lowPrice ?? null,
      previousClose: quote?.previousClose ?? null,
      volume: quote?.volume ?? null,
      amount: quote?.amount ?? null,
    } satisfies StockQuoteSnapshot;
  });
}

export async function getStockKLine(code: string, options?: { exchange?: string | null; limit?: number; adjust?: 0 | 1 | 2 }) {
  const cleanCode = normalizeStockCode(code);
  const secId = toSecId(cleanCode, options?.exchange ?? null);
  const limit = Math.min(Math.max(Number(options?.limit ?? 1200), 60), 2000);
  const adjust = options?.adjust ?? 1;
  const klineUrl = `https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=${encodeURIComponent(secId)}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=${adjust}&end=20500101&lmt=${limit}`;
  const payload = await fetchJson<RawKLineResponse>(klineUrl, {
    headers: {
      referer: `https://quote.eastmoney.com/concept/${cleanCode}.html`,
    },
  });

  const items = (payload.data?.klines ?? [])
    .map((line) => parseKLinePoint(line))
    .filter((item): item is StockKLinePoint => Boolean(item && item.date));

  return {
    code: cleanCode,
    name: payload.data?.name?.trim() || null,
    exchange: inferExchange(cleanCode, secId),
    secId,
    items,
  };
}

export async function getStockDetail(code: string, options?: { exchange?: string | null; klineLimit?: number }): Promise<StockDetailResponse> {
  const cleanCode = normalizeStockCode(code);
  const [quotes, klinePayload] = await Promise.all([
    getRealtimeStockQuotes([{ code: cleanCode, exchange: options?.exchange ?? null }]),
    getStockKLine(cleanCode, { exchange: options?.exchange ?? null, limit: options?.klineLimit ?? 1200 }),
  ]);
  const quote = quotes[0] ?? null;
  const latestCandle = klinePayload.items.at(-1) ?? null;
  const previousCandle = klinePayload.items.at(-2) ?? null;
  const exchange = quote?.exchange ?? klinePayload.exchange ?? inferExchangeFromCode(cleanCode);
  const stock: StockMeta = {
    code: cleanCode,
    name: quote?.name ?? klinePayload.name ?? cleanCode,
    exchange,
    secId: quote?.secId ?? klinePayload.secId,
    latestTradeDate: latestCandle?.date ?? new Date().toISOString().slice(0, 10),
    latestPrice: quote?.latestPrice ?? latestCandle?.close ?? null,
    latestClose: latestCandle?.close ?? null,
    openPrice: quote?.openPrice ?? latestCandle?.open ?? null,
    highPrice: quote?.highPrice ?? latestCandle?.high ?? null,
    lowPrice: quote?.lowPrice ?? latestCandle?.low ?? null,
    previousClose: quote?.previousClose ?? previousCandle?.close ?? null,
    changeRate: quote?.changeRate ?? latestCandle?.changeRate ?? null,
    changeAmount: quote?.changeAmount ?? latestCandle?.changeAmount ?? null,
    volume: quote?.volume ?? latestCandle?.volume ?? null,
    amount: quote?.amount ?? latestCandle?.amount ?? null,
    turnoverRate: latestCandle?.turnoverRate ?? null,
    amplitude: latestCandle?.amplitude ?? null,
  };

  return {
    stock,
    performance: buildPricePerformanceSummary(klinePayload.items),
    kline: klinePayload.items,
  };
}

export async function getFundHoldingStocks(fundCode: string, topline = 10): Promise<FundHoldingStocksLookupResponse> {
  const cleanCode = normalizeFundCode(fundCode);
  const safeTopline = Math.min(Math.max(Number(topline || 10), 1), 50);
  const holdingsUrl = `https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc&code=${cleanCode}&topline=${safeTopline}&year=&month=`;
  const holdingsText = await fetchText(holdingsUrl, {
    headers: {
      referer: `https://fundf10.eastmoney.com/jjcc_${cleanCode}.html`,
    },
  }).catch(() => "");

  const parsed = holdingsText ? parseLatestFundHoldings(holdingsText) : { reportDate: null, items: [] };
  const quotes = parsed.items.length > 0 ? await getRealtimeStockQuotes(parsed.items).catch(() => []) : [];
  const quoteMap = new Map(quotes.map((item) => [item.code, item]));

  return {
    fundCode: cleanCode,
    reportDate: parsed.reportDate,
    items: parsed.items.map(({ secId: _secId, ...item }) => {
      const quote = quoteMap.get(item.code);
      return {
        ...item,
        name: quote?.name ?? item.name,
        exchange: quote?.exchange ?? item.exchange,
        latestPrice: quote?.latestPrice ?? item.latestPrice,
        changeRate: quote?.changeRate ?? item.changeRate,
        changeAmount: quote?.changeAmount ?? item.changeAmount,
      } satisfies FundHoldingStock;
    }),
  };
}
