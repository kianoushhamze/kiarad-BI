// Iranian sales channels grouped by how they work. Facts are limited to what
// public sources state; anything that needs the platform's confirmation says so.
export type MarketModel = "marketplace" | "compare" | "ads";

export type MarketplaceInfo = {
  id: string;
  name: string;
  model: MarketModel;
  orderPlace: string;
  need: string;
  ourSide: string;
  status: "connected" | "feed_ready" | "needs_account";
  priority: 1 | 2 | 3;
};

export const modelLabel: Record<MarketModel, string> = {
  marketplace: "بازارگاه (سفارش داخل خودش)",
  compare: "مقایسهٔ قیمت (خریدار به سایت ما می‌آید)",
  ads: "آگهی (توافق مستقیم)",
};

export const statusLabel: Record<MarketplaceInfo["status"], string> = {
  connected: "متصل",
  feed_ready: "فید آماده؛ ثبت فروشگاه لازم است",
  needs_account: "حساب فروشنده لازم است",
};

export const MARKETPLACES: MarketplaceInfo[] = [
  { id: "digikala", name: "دیجی‌کالا", model: "marketplace", orderPlace: "داخل دیجی‌کالا", need: "پنل فروشنده (موجود است)", ourSide: "نگاشت کالا، قیمت و موجودی و ثبت سفارش در هلو", status: "connected", priority: 1 },
  { id: "torob", name: "ترب", model: "compare", orderPlace: "سایت خودمان", need: "ثبت فروشگاه در sellers.torob.com، سایت فعال، اینماد و درگاه پرداخت؛ تأیید فنی توسط خود ترب", ourSide: "/public/feeds/torob (قالب API نسخهٔ ۲) و لینک مستقیم کالا", status: "feed_ready", priority: 1 },
  { id: "emalls", name: "ایمالز", model: "compare", orderPlace: "سایت خودمان", need: "ثبت فروشگاه و تأیید روش دریافت فهرست از خود ایمالز", ourSide: "/public/feeds/products.json و products.csv؛ قالب دقیق باید با ایمالز تأیید شود", status: "feed_ready", priority: 1 },
  { id: "basalam", name: "باسلام", model: "marketplace", orderPlace: "داخل باسلام", need: "ایجاد غرفه و بررسی پذیرش دستهٔ آرایشی‌بهداشتی؛ مستندات وب‌سرویس باسلام منتشر شده است", ourSide: "پس از غرفه: رابط سفارش و موجودی مثل دیجی‌کالا (در platform_sync)", status: "needs_account", priority: 2 },
  { id: "snappshop", name: "اسنپ‌شاپ", model: "marketplace", orderPlace: "داخل اسنپ‌شاپ", need: "درخواست همکاری؛ پذیرش و کمیسیون طبق توافق", ourSide: "پس از توافق و دریافت روش فنی", status: "needs_account", priority: 3 },
  { id: "divar", name: "دیوار (فروشگاه)", model: "ads", orderPlace: "توافق مستقیم", need: "بستهٔ آگهی فروشگاهی", ourSide: "بدون همگام‌سازی سفارش؛ فقط آگهی با لینک سایت", status: "needs_account", priority: 3 },
  { id: "isam", name: "ایسام", model: "marketplace", orderPlace: "داخل ایسام", need: "حساب فروشنده؛ بیشتر برای کالای خاص و مزایده", ourSide: "فعلاً دستی", status: "needs_account", priority: 3 },
];
