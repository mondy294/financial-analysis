/** 纯前端指标，周/月 K 或库内特征缺失时使用。 */

export function sma(closes: number[], period: number): Array<number | null> {
  const out: Array<number | null> = Array(closes.length).fill(null);
  let sum = 0;
  for (let i = 0; i < closes.length; i++) {
    sum += closes[i];
    if (i >= period) sum -= closes[i - period];
    if (i >= period - 1) out[i] = sum / period;
  }
  return out;
}

export function bollinger(
  closes: number[],
  period = 20,
  mult = 2,
): { mid: Array<number | null>; upper: Array<number | null>; lower: Array<number | null> } {
  const mid = sma(closes, period);
  const upper: Array<number | null> = Array(closes.length).fill(null);
  const lower: Array<number | null> = Array(closes.length).fill(null);
  for (let i = period - 1; i < closes.length; i++) {
    const m = mid[i];
    if (m == null) continue;
    let varSum = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const d = closes[j] - m;
      varSum += d * d;
    }
    const std = Math.sqrt(varSum / period);
    upper[i] = m + mult * std;
    lower[i] = m - mult * std;
  }
  return { mid, upper, lower };
}

function ema(closes: number[], period: number): Array<number | null> {
  const out: Array<number | null> = Array(closes.length).fill(null);
  if (!closes.length) return out;
  const k = 2 / (period + 1);
  let prev = closes[0];
  out[0] = prev;
  for (let i = 1; i < closes.length; i++) {
    prev = closes[i] * k + prev * (1 - k);
    out[i] = prev;
  }
  return out;
}

export function macd(closes: number[]): {
  dif: Array<number | null>;
  dea: Array<number | null>;
  hist: Array<number | null>;
} {
  const ema12 = ema(closes, 12);
  const ema26 = ema(closes, 26);
  const dif: Array<number | null> = closes.map((_, i) => {
    if (ema12[i] == null || ema26[i] == null) return null;
    return (ema12[i] as number) - (ema26[i] as number);
  });
  const difNums = dif.map((v) => v ?? 0);
  const deaRaw = ema(difNums, 9);
  // 前段 DIF 未稳定时 DEA 也标 null
  const dea = deaRaw.map((v, i) => (dif[i] == null ? null : v));
  const hist = dif.map((d, i) => {
    if (d == null || dea[i] == null) return null;
    return d - (dea[i] as number);
  });
  return { dif, dea, hist };
}

export function rsi(closes: number[], period = 14): Array<number | null> {
  const out: Array<number | null> = Array(closes.length).fill(null);
  if (closes.length <= period) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= period; i++) {
    const ch = closes[i] - closes[i - 1];
    if (ch >= 0) gain += ch;
    else loss -= ch;
  }
  let avgGain = gain / period;
  let avgLoss = loss / period;
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = period + 1; i < closes.length; i++) {
    const ch = closes[i] - closes[i - 1];
    const g = ch > 0 ? ch : 0;
    const l = ch < 0 ? -ch : 0;
    avgGain = (avgGain * (period - 1) + g) / period;
    avgLoss = (avgLoss * (period - 1) + l) / period;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}
