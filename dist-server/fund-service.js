const USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36";
const API_HEADERS = {
    "user-agent": USER_AGENT,
    accept: "application/json, text/plain, */*",
};
const CACHE_TTL_MS = 2 * 60 * 1000;
const cache = new Map();
function parseNumber(value) {
    if (value === null || value === undefined || value === "") {
        return null;
    }
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
}
function extractQuotedVar(source, variableName) {
    const matcher = source.match(new RegExp(`var\\s+${variableName}\\s*=\\s*\"([^\"]*)\";`));
    return matcher?.[1] ?? null;
}
function extractArrayVar(source, variableName) {
    const matcher = source.match(new RegExp(`var\\s+${variableName}\\s*=\\s*(\\[[\\s\\S]*?\\]);`));
    if (!matcher?.[1]) {
        return null;
    }
    return JSON.parse(matcher[1]);
}
function toDateString(timestamp) {
    return new Date(timestamp).toISOString().slice(0, 10);
}
function shiftDate(baseDate, options) {
    const date = new Date(`${baseDate}T00:00:00`);
    if (options.days) {
        date.setDate(date.getDate() - options.days);
    }
    if (options.months) {
        date.setMonth(date.getMonth() - options.months);
    }
    return date;
}
function findClosestPoint(points, targetDate) {
    const targetTimestamp = targetDate.getTime();
    let matched = points[0];
    for (const point of points) {
        if (new Date(`${point.date}T00:00:00`).getTime() <= targetTimestamp) {
            matched = point;
            continue;
        }
        break;
    }
    return matched;
}
function calculateReturn(points, targetDate) {
    if (points.length < 2) {
        return null;
    }
    const latest = points.at(-1);
    const base = findClosestPoint(points, targetDate);
    if (!latest?.nav || !base?.nav || base.nav === 0) {
        return null;
    }
    return Number((((latest.nav - base.nav) / base.nav) * 100).toFixed(2));
}
function parseEstimate(rawText) {
    const matcher = rawText.match(/jsonpgz\((.*)\);?/);
    if (!matcher?.[1]) {
        return null;
    }
    return JSON.parse(matcher[1]);
}
async function fetchText(url, init) {
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
async function fetchJson(url, init) {
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
    return response.json();
}
async function requestFundPerformance(code) {
    const timestamp = Date.now();
    const detailUrl = `https://fund.eastmoney.com/pingzhongdata/${code}.js?v=${timestamp}`;
    const estimateUrl = `https://fundgz.1234567.com.cn/js/${code}.js?rt=${timestamp}`;
    const historyUrl = `https://api.fund.eastmoney.com/f10/lsjz?fundCode=${code}&pageIndex=1&pageSize=30`;
    const [detailText, estimateText, historyPayload] = await Promise.all([
        fetchText(detailUrl, {
            headers: {
                referer: `https://fundf10.eastmoney.com/jbgk_${code}.html`,
            },
        }),
        fetchText(estimateUrl, {
            headers: {
                referer: "https://fundgz.1234567.com.cn/",
            },
        }).catch(() => ""),
        fetchJson(historyUrl, {
            headers: {
                referer: `https://fundf10.eastmoney.com/jjjz_${code}.html`,
            },
        }),
    ]);
    const fundName = extractQuotedVar(detailText, "fS_name");
    const sourceRate = extractQuotedVar(detailText, "fund_sourceRate");
    const currentRate = extractQuotedVar(detailText, "fund_Rate");
    const rawTrend = extractArrayVar(detailText, "Data_netWorthTrend") ?? [];
    const estimate = estimateText ? parseEstimate(estimateText) : null;
    const navHistoryRaw = historyPayload.Data?.LSJZList ?? [];
    if (!fundName || rawTrend.length === 0 || navHistoryRaw.length === 0) {
        throw new Error("没有查到这只基金，或者基金数据暂时不可用。");
    }
    const trend = rawTrend
        .map((point) => ({
        date: toDateString(point.x),
        nav: parseNumber(point.y),
    }))
        .filter((point) => point.nav !== null);
    const latestTrendPoint = trend.at(-1);
    if (!latestTrendPoint?.nav) {
        throw new Error("基金趋势数据不完整，暂时无法展示。");
    }
    const latestDate = latestTrendPoint.date;
    const yearStart = new Date(`${latestDate.slice(0, 4)}-01-01T00:00:00`);
    const navHistory = navHistoryRaw.map((item) => ({
        date: item.FSRQ,
        unitNav: parseNumber(item.DWJZ),
        cumulativeNav: parseNumber(item.LJJZ),
        dailyGrowthRate: parseNumber(item.JZZZL),
        purchaseStatus: item.SGZT || null,
        redemptionStatus: item.SHZT || null,
    }));
    const historyValues = navHistory
        .map((item) => item.unitNav)
        .filter((value) => value !== null);
    return {
        fund: {
            code,
            name: fundName,
            latestNavDate: navHistory[0]?.date ?? latestDate,
            latestNav: navHistory[0]?.unitNav ?? latestTrendPoint.nav,
            latestCumulativeNav: navHistory[0]?.cumulativeNav ?? null,
            latestDailyGrowthRate: navHistory[0]?.dailyGrowthRate ?? null,
            estimatedNav: parseNumber(estimate?.gsz),
            estimatedChangeRate: parseNumber(estimate?.gszzl),
            estimateTime: estimate?.gztime ?? null,
            purchaseStatus: navHistory[0]?.purchaseStatus ?? null,
            redemptionStatus: navHistory[0]?.redemptionStatus ?? null,
            sourceRate,
            currentRate,
        },
        performance: {
            oneWeek: calculateReturn(trend, shiftDate(latestDate, { days: 7 })),
            oneMonth: calculateReturn(trend, shiftDate(latestDate, { months: 1 })),
            threeMonths: calculateReturn(trend, shiftDate(latestDate, { months: 3 })),
            sixMonths: calculateReturn(trend, shiftDate(latestDate, { months: 6 })),
            oneYear: calculateReturn(trend, shiftDate(latestDate, { months: 12 })),
            yearToDate: calculateReturn(trend, yearStart),
            sinceInception: calculateReturn(trend, new Date(`${trend[0].date}T00:00:00`)),
            lowestRecentNav: historyValues.length ? Math.min(...historyValues) : null,
            highestRecentNav: historyValues.length ? Math.max(...historyValues) : null,
        },
        navHistory,
        trend,
    };
}
export async function getFundPerformance(code) {
    const cleanCode = code.trim();
    if (!/^\d{6}$/.test(cleanCode)) {
        throw new Error("基金编号必须是 6 位数字。");
    }
    const hit = cache.get(cleanCode);
    if (hit && hit.expiresAt > Date.now()) {
        return hit.value;
    }
    const value = await requestFundPerformance(cleanCode);
    cache.set(cleanCode, {
        value,
        expiresAt: Date.now() + CACHE_TTL_MS,
    });
    return value;
}
