const TEHRAN = "Asia/Tehran";
const PERSIAN_LOCALE = "fa-IR-u-ca-persian-nu-arabext";
const PERSIAN_INPUT_LOCALE = "en-US-u-ca-persian-nu-latn";
const persianInputFormatter = new Intl.DateTimeFormat(PERSIAN_INPUT_LOCALE, {
  timeZone: TEHRAN,
  year: "numeric",
  month: "numeric",
  day: "numeric",
});

function persianDateParts(date: Date) {
  const parts = persianInputFormatter.formatToParts(date);
  return {
    year: Number(parts.find(part => part.type === "year")?.value),
    month: Number(parts.find(part => part.type === "month")?.value),
    day: Number(parts.find(part => part.type === "day")?.value),
  };
}

function normalizeDigits(value: string): string {
  return value.replace(/[۰-۹٠-٩]/g, digit => String("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩".indexOf(digit) % 10));
}

export function formatJalaliDateInput(value: string | Date): string {
  const date = asDate(value);
  if (Number.isNaN(date.getTime())) return "";
  const { year, month, day } = persianDateParts(date);
  return `${year}/${String(month).padStart(2, "0")}/${String(day).padStart(2, "0")}`
    .replace(/\d/g, digit => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);
}

export function jalaliDateInputToIso(value: string): string | null {
  const match = normalizeDigits(value.trim()).match(/^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})$/);
  if (!match) return null;
  const [, yearText, monthText, dayText] = match;
  const target = { year: Number(yearText), month: Number(monthText), day: Number(dayText) };
  if (target.year < 1200 || target.year > 1600 || target.month < 1 || target.month > 12 || target.day < 1 || target.day > 31) return null;

  // Search the two Gregorian years that can contain this Persian calendar year.
  const firstDay = Date.UTC(target.year + 621, 0, 1, 12);
  const endDay = Date.UTC(target.year + 623, 0, 1, 12);
  for (let timestamp = firstDay; timestamp < endDay; timestamp += 86_400_000) {
    const parts = persianDateParts(new Date(timestamp));
    if (parts.year === target.year && parts.month === target.month && parts.day === target.day) {
      return new Date(timestamp).toISOString().slice(0, 10);
    }
  }
  return null;
}

function asDate(value: string | Date): Date {
  if (value instanceof Date) return value;
  // Treat date-only values as local calendar dates, not UTC midnight.
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return validIsoCalendarDate(value) ? new Date(`${value}T12:00:00+03:30`) : new Date(NaN);
  }
  return new Date(value);
}

function validIsoCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T12:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

function calendarInputToIsoDate(value: string): string | null {
  const year = value.match(/^(\d{4})[/.\-]/)?.[1];
  // The supported Persian input years take precedence over the ISO-shaped separator.
  if (year && Number(year) >= 1200 && Number(year) <= 1600) return jalaliDateInputToIso(value);
  return validIsoCalendarDate(value) ? value : null;
}

export function formatIranDate(value: string | Date): string {
  const date = asDate(value);
  if (Number.isNaN(date.getTime())) return "تاریخ نامعتبر";
  return new Intl.DateTimeFormat(PERSIAN_LOCALE, {
    timeZone: TEHRAN,
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date);
}

// Imported period labels may already be Persian dates or descriptive text.
export function formatIranReportPeriod(value?: string | null): string {
  const label = value?.trim();
  if (!label) return "—";
  return /^(19|20)\d{2}-\d{2}-\d{2}$/.test(label) ? formatIranDate(label) : label;
}

export function formatIranDateTime(value: string | Date): string {
  const date = asDate(value);
  if (Number.isNaN(date.getTime())) return "تاریخ نامعتبر";
  return new Intl.DateTimeFormat(PERSIAN_LOCALE, {
    timeZone: TEHRAN,
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatIranTime(value: string | Date): string {
  const date = asDate(value);
  if (Number.isNaN(date.getTime())) return "زمان نامعتبر";
  return new Intl.DateTimeFormat(PERSIAN_LOCALE, {
    timeZone: TEHRAN,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

export function iranTodayIso(): string {
  return new Intl.DateTimeFormat("en-CA-u-ca-gregory", {
    timeZone: TEHRAN,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export function iranCurrentMonthIso(): string {
  return new Intl.DateTimeFormat("en-CA-u-ca-gregory", {
    timeZone: TEHRAN,
    year: "numeric",
    month: "2-digit",
  }).format(new Date());
}

export function iranDateInputToIso(value: string): string | null {
  const normalized = normalizeDigits(value.trim());
  const isoDate = calendarInputToIsoDate(normalized);
  if (!isoDate || !validIsoCalendarDate(isoDate)) return null;
  const date = new Date(`${isoDate}T12:00:00+03:30`);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export function iranDateTimeInputToIso(value: string): string | null {
  const normalized = normalizeDigits(value.trim());
  const timestamp = normalized.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-](\d{2}):(\d{2}))$/);
  if (timestamp) {
    const [, dateText, hourText, minuteText, secondText, , offsetHourText, offsetMinuteText] = timestamp;
    // Zoned timestamps are explicitly Gregorian; Date must not normalize 24:00 to tomorrow.
    if (!validIsoCalendarDate(dateText) || Number(hourText) > 23 || Number(minuteText) > 59 ||
        Number(secondText ?? 0) > 59 || Number(offsetHourText ?? 0) > 23 || Number(offsetMinuteText ?? 0) > 59) return null;
    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
  }
  const match = normalized.match(/^(.+)[T ](\d{1,2}):(\d{2})$/);
  if (!match) return null;
  const [, dateText, hourText, minuteText] = match;
  const isoDate = calendarInputToIsoDate(dateText);
  const hour = Number(hourText), minute = Number(minuteText);
  if (!isoDate || !validIsoCalendarDate(isoDate) || hour > 23 || minute > 59) return null;
  const date = new Date(`${isoDate}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00+03:30`);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export function formatIranDateTimeInput(value: string | Date): string {
  const date = asDate(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat(PERSIAN_INPUT_LOCALE, {
    timeZone: TEHRAN,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const valueFor = (type: Intl.DateTimeFormatPartTypes) => parts.find(part => part.type === type)?.value ?? "";
  return `${valueFor("year")}/${valueFor("month")}/${valueFor("day")} ${valueFor("hour")}:${valueFor("minute")}`
    .replace(/\d/g, digit => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);
}
