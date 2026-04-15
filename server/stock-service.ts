import type { FundHoldingStock, FundHoldingStocksLookupResponse, StockQuoteSnapshot } from "./types.js";

type RawHoldingQuoteItem = {
  f12?: string;
  f14?: string;
  f2?: number | string;
  f3?: number | string;
  f4?: number | string;
};

type RawHoldingQuoteResponse = {
  data?: {
    diff?: RawHoldingQuoteItem[];
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
  const quoteUrl = `https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&invt=2&fields=f12,f14,f2,f3,f4,f18&secids=${encodeURIComponent(secids)}`;
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
    } satisfies StockQuoteSnapshot;
  });
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
