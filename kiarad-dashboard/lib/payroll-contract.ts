export type MoneyUnit = "rial" | "toman";
export type RuleTier = { up_to_amount: string | null; percent: string };
export type RuleTarget = { target_type: "brand" | "product"; item_identifier: string; item_title: string; target_amount: string; target_quantity: string; commission_percent: string; target_gate: "all" | "any" | null; commission_basis: "whole" | "excess" | null };
export type RulesForm = {
  salary_mode: "hourly" | "fixed" | "commission_only";
  fixed_monthly_amount: string; fixed_proration: "full" | "working_days" | null;
  required_workdays: string | null; hourly_rate: string; min_monthly_hours: string;
  overtime_multiplier: string | null; settlement_commission_percent: string;
  daily_mission_allowance: string; per_km_rate: string; sales_scope: "personal";
  commission_tier_basis: "marginal"; commission_overlap: "highest" | "sum" | null;
  sales_tiers: RuleTier[]; targets: RuleTarget[]; content_bonus?: Record<string, unknown>; bonus_note: string;
};

export const normalizeNumberText = (value: string) => value.trim()
  .replace(/[۰-۹٠-٩]/g, digit => String("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩".indexOf(digit) % 10))
  .replace(/[٬,]/g, "").replace(/٫/g, ".");

export function shiftDecimal(value: string, places: number): string {
  const normalized = normalizeNumberText(value);
  if (!normalized || !/^\d*(?:\.\d*)?$/.test(normalized) || !/\d/.test(normalized)) return normalized;
  const [whole = "0", fraction = ""] = normalized.split(".");
  const digits = (whole || "0") + fraction;
  const position = (whole || "0").length + places;
  const shifted = position <= 0 ? "0." + "0".repeat(-position) + digits
    : position >= digits.length ? digits + "0".repeat(position - digits.length)
    : digits.slice(0, position) + "." + digits.slice(position);
  return shifted.replace(/^0+(?=\d)/, "").replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

export const displayMoney = (rials: string, unit: MoneyUnit) => shiftDecimal(rials, unit === "toman" ? -1 : 0);
export const inputMoney = (value: string, unit: MoneyUnit) => shiftDecimal(value, unit === "toman" ? 1 : 0);
export const record = (value: unknown): Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
const scalar = (value: unknown, fallback = "0") => typeof value === "string" || typeof value === "number" ? String(value) : fallback;

export function emptyRules(): RulesForm {
  return { salary_mode: "hourly", fixed_monthly_amount: "0", fixed_proration: null, required_workdays: null,
    hourly_rate: "0", min_monthly_hours: "0", overtime_multiplier: null, settlement_commission_percent: "0",
    daily_mission_allowance: "0", per_km_rate: "0", sales_scope: "personal", commission_tier_basis: "marginal",
    commission_overlap: null, sales_tiers: [], targets: [], bonus_note: "" };
}

export function parseRules(value: unknown): RulesForm {
  const source = record(value), form = emptyRules();
  form.salary_mode = source.salary_mode === "fixed" || source.salary_mode === "commission_only" ? source.salary_mode : "hourly";
  form.fixed_proration = source.fixed_proration === "full" || source.fixed_proration === "working_days" ? source.fixed_proration : null;
  form.commission_overlap = source.commission_overlap === "highest" || source.commission_overlap === "sum" ? source.commission_overlap : null;
  for (const key of ["fixed_monthly_amount", "hourly_rate", "min_monthly_hours", "settlement_commission_percent", "daily_mission_allowance", "per_km_rate"] as const) form[key] = scalar(source[key]);
  form.required_workdays = source.required_workdays == null ? null : scalar(source.required_workdays);
  form.overtime_multiplier = source.overtime_multiplier == null ? null : scalar(source.overtime_multiplier);
  form.bonus_note = typeof source.bonus_note === "string" ? source.bonus_note : "";
  form.sales_tiers = Array.isArray(source.sales_tiers) ? source.sales_tiers.map(value => { const tier = record(value); return { up_to_amount: tier.up_to_amount == null ? null : scalar(tier.up_to_amount), percent: scalar(tier.percent, "") }; }) : [];
  form.targets = Array.isArray(source.targets) ? source.targets.map(value => {
    const target = record(value);
    return { target_type: target.target_type === "product" ? "product" : "brand", item_identifier: scalar(target.item_identifier, ""), item_title: scalar(target.item_title, ""),
      target_amount: scalar(target.target_amount), target_quantity: scalar(target.target_quantity), commission_percent: scalar(target.commission_percent),
      target_gate: target.target_gate === "all" || target.target_gate === "any" ? target.target_gate : null,
      commission_basis: target.commission_basis === "whole" || target.commission_basis === "excess" ? target.commission_basis : null };
  }) : [];
  if (source.content_bonus && Object.keys(record(source.content_bonus)).length) form.content_bonus = record(source.content_bonus);
  return form;
}

export function currentPersianMonth() {
  const parts = new Intl.DateTimeFormat("en-US-u-ca-persian-nu-latn", { timeZone: "Asia/Tehran", year: "numeric", month: "2-digit" }).formatToParts(new Date());
  return `${parts.find(part => part.type === "year")?.value}-${parts.find(part => part.type === "month")?.value}`;
}

export function validPersianMonth(value: string) {
  const normalized = normalizeNumberText(value).replace("/", "-");
  const match = normalized.match(/^(\d{4})-(\d{2})$/);
  return !!match && Number(match[1]) >= 1200 && Number(match[1]) <= 1600 && Number(match[2]) >= 1 && Number(match[2]) <= 12;
}

export function validateForm(form: RulesForm): string | null {
  const numbers: Array<[string, string | null]> = [["حقوق ثابت", form.fixed_monthly_amount], ["نرخ ساعتی", form.hourly_rate], ["ساعت موظفی", form.min_monthly_hours], ["ضریب اضافه‌کار", form.overtime_multiplier], ["روز موظفی", form.required_workdays], ["درصد وصول", form.settlement_commission_percent], ["مأموریت روزانه", form.daily_mission_allowance], ["نرخ کیلومتر", form.per_km_rate]];
  for (const tier of form.sales_tiers) numbers.push(["سقف پله", tier.up_to_amount], ["درصد پله", tier.percent]);
  for (const target of form.targets) numbers.push(["مبلغ هدف", target.target_amount], ["تعداد هدف", target.target_quantity], ["درصد هدف", target.commission_percent]);
  for (const [name, value] of numbers) if (value !== null && !/^\d+(?:\.\d+)?$/.test(normalizeNumberText(value))) return `${name} باید عدد غیرمنفی معتبر باشد.`;
  return null;
}
