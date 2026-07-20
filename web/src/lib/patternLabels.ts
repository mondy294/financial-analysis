/** 策略中英文名展示（id 稳定；名称来自 meta / definitions） */

export type PatternNameFields = {
  id?: string;
  display_name?: string | null;
  display_name_en?: string | null;
};

export type PatternMetaLike = PatternNameFields & { id: string };

/** 中文名（缺省回退 id） */
export function patternNameZh(
  id: string | null | undefined,
  meta?: PatternNameFields | null,
): string {
  const zh = (meta?.display_name || "").trim();
  if (zh) return zh;
  return (id || meta?.id || "—").toString();
}

/** 英文名（可空） */
export function patternNameEn(meta?: PatternNameFields | null): string {
  return (meta?.display_name_en || "").trim();
}

/**
 * 统一标签：有英文则「中文 / English」，否则中文；可附带 id。
 * @example patternLabel("RANGE_BREAKOUT", meta) → "横盘突破 / Range Breakout"
 */
export function patternLabel(
  id: string | null | undefined,
  meta?: PatternNameFields | null,
  opts?: { withId?: boolean },
): string {
  const pid = (id || meta?.id || "").toString();
  const zh = patternNameZh(pid, meta);
  const en = patternNameEn(meta);
  let label = en && en !== zh ? `${zh} / ${en}` : zh;
  if (opts?.withId && pid && pid !== zh) {
    label = `${label} (${pid})`;
  }
  return label;
}

export function buildPatternMetaMap(
  items: PatternMetaLike[] | null | undefined,
): Map<string, PatternMetaLike> {
  const map = new Map<string, PatternMetaLike>();
  for (const p of items || []) {
    if (p?.id) map.set(p.id.toUpperCase(), p);
  }
  return map;
}

export function lookupPatternMeta(
  map: Map<string, PatternMetaLike>,
  id: string | null | undefined,
): PatternMetaLike | undefined {
  if (!id) return undefined;
  return map.get(id.toUpperCase());
}
