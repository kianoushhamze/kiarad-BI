export type Salesperson = {
  id: number;
  name?: string;
  full_name?: string;
  [key: string]: unknown;
};

export type CompensationTarget = {
  target_type: string;
  item_identifier: string;
  item_title: string;
  target_amount: number;
  target_quantity: number;
  commission_percent: number;
};

export type CompensationSettings = {
  configured: boolean;
  hourlyRate: number;
  minHours: number;
  settlementPercent: number;
  dailyMission: number;
  perKmRate: number;
  targets: CompensationTarget[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finiteNumber(value: unknown, fallback = 0): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function parseSalespeople(value: unknown): Salesperson[] {
  let candidates: unknown = value;
  if (!Array.isArray(candidates) && isRecord(candidates)) {
    for (const key of ["salespersons", "items", "data", "result"]) {
      if (Array.isArray(candidates[key])) {
        candidates = candidates[key];
        break;
      }
    }
  }
  if (!Array.isArray(candidates)) return [];

  return candidates.flatMap((candidate): Salesperson[] => {
    if (!isRecord(candidate) || typeof candidate.id !== "number" || !Number.isFinite(candidate.id)) return [];
    const person: Salesperson = { id: candidate.id };
    if (typeof candidate.name === "string") person.name = candidate.name;
    if (typeof candidate.full_name === "string") person.full_name = candidate.full_name;
    return [person];
  });
}

export function parseCompensationTargets(value: unknown): CompensationTarget[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((candidate): CompensationTarget[] => {
    if (!isRecord(candidate)) return [];
    return [{
      target_type: typeof candidate.target_type === "string" ? candidate.target_type : "brand",
      item_identifier: typeof candidate.item_identifier === "string" ? candidate.item_identifier : "",
      item_title: typeof candidate.item_title === "string" ? candidate.item_title : "",
      target_amount: finiteNumber(candidate.target_amount),
      target_quantity: finiteNumber(candidate.target_quantity),
      commission_percent: finiteNumber(candidate.commission_percent),
    }];
  });
}

export function parseCompensationSettings(value: unknown): CompensationSettings | null {
  if (!isRecord(value)) return null;
  return {
    configured: value.configured === true,
    hourlyRate: finiteNumber(value.hourly_rate),
    minHours: finiteNumber(value.min_monthly_hours, 176),
    settlementPercent: finiteNumber(value.settlement_commission_percent),
    dailyMission: finiteNumber(value.daily_mission_allowance),
    perKmRate: finiteNumber(value.per_km_rate),
    targets: parseCompensationTargets(value.targets),
  };
}
