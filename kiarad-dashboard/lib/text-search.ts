/** Search only: display names and stored free text are never rewritten. */
export function normalizeSearchText(value: unknown): string {
  return String(value ?? "").normalize("NFKC")
    .replace(/[يى]/g, "ی").replace(/ك/g, "ک").replace(/[آأإ]/g, "ا")
    .replace(/[۰-۹٠-٩]/g, digit => String("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩".indexOf(digit) % 10))
    .replace(/[ـ\u064b-\u065f\u0670]/g, "")
    .replace(/[\u200c\u200d\u200e\u200f]/g, " ")
    .replace(/[^\p{L}\p{N}]+/gu, " ").trim().toLowerCase();
}

export function matchesSearch(query: string, ...values: unknown[]): boolean {
  const tokens = normalizeSearchText(query).split(/\s+/).filter(Boolean);
  const text = normalizeSearchText(values.join(" "));
  const compact = text.replace(/\s+/g, "");
  return tokens.every(token => text.includes(token) || compact.includes(token));
}

export function uniqueSearchOptions(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  return values.flatMap(value => {
    const original = value?.trim() ?? "";
    const normalized = normalizeSearchText(original);
    if (!normalized || seen.has(normalized)) return [];
    seen.add(normalized);
    return [original];
  });
}
