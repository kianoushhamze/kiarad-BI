const months = [
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
];

const salesPeople = [
  ["آنتیا کریمی", "۴۲", "م.ت"],
  ["یونس رضایی", "۳۸", "م.ت"],
  ["مهران ایرانمنش", "۳۳", "م.ت"],
];

const inventory = [
  ["موتور صنعتی", "کد ۲۱۴", 88, "green"],
  ["محفظه فولادی", "کد ۰۹۲", 64, "green"],
  ["چرخ دنده دقیق", "کد ۳۷۱", 28, "pink"],
  ["سیم مسی", "کد ۵۵۸", 46, "yellow"],
  ["برد کنترل", "کد ۱۱۰", 12, "pink"],
];

const activities = [
  ["گزارش فروش روزانه آماده شد", "۲ دقیقه پیش", "green"],
  ["پیشنهاد قیمت‌گذاری جدید ایجاد شد", "۱۴ دقیقه پیش", "purple"],
  ["هشدار تأخیر در ارسال سفارش #۴۵۷۸", "۲۸ دقیقه پیش", "pink"],
  ["تحلیل پیش‌بینی فروش تکمیل شد", "۳۸ دقیقه پیش", "blue"],
  ["اجرای برنامه هفتگی انجام شد", "۵۴ دقیقه پیش", "yellow"],
];

export default function Home() {
  return (
    <main dir="rtl" className="min-h-screen bg-[#070709] text-white">
      <div className="mx-auto max-w-[1700px] px-6 py-5">

        {/* HEADER */}
        <header className="mb-7 flex items-center justify-between border-b border-white/[0.06] pb-5">

          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-indigo-700 text-lg font-bold shadow-lg shadow-violet-900/30">
              K
            </div>

            <div>
              <div className="text-base font-bold tracking-tight">
                Kiarad BI
              </div>
              <div className="mt-0.5 text-[10px] text-zinc-600">
                Business Intelligence
              </div>
            </div>
          </div>

          <nav className="hidden items-center gap-8 text-xs lg:flex">
            <span className="relative text-white">
              داشبورد
              <span className="absolute -bottom-5 right-0 left-0 mx-auto h-0.5 rounded-full bg-violet-500" />
            </span>

            <span className="text-zinc-500 hover:text-zinc-200">
              فروش
            </span>

            <span className="text-zinc-500 hover:text-zinc-200">
              مشتریان
            </span>

            <span className="text-zinc-500 hover:text-zinc-200">
              انبار
            </span>

            <span className="text-zinc-500 hover:text-zinc-200">
              مالی
            </span>

            <span className="text-zinc-500 hover:text-zinc-200">
              گزارش‌ها
            </span>
          </nav>

          <div className="flex items-center gap-2">

            <button className="hidden rounded-xl border border-white/[0.07] bg-[#101012] px-4 py-2.5 text-xs text-zinc-400 sm:block">
              امروز
            </button>

            <button className="rounded-xl bg-violet-600 px-4 py-2.5 text-xs font-medium shadow-lg shadow-violet-900/20 hover:bg-violet-500">
              ✦ دستیار هوشمند
            </button>

          </div>

        </header>

        {/* KPI */}
        <section className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-5">

          {[
            ["فروش امروز", "۸۷.۳ م", "+۱۲.۲٪", "violet"],
            ["فروش ماه", "۹۸۷.۳ م", "+۸.۷٪", "cyan"],
            ["سود ناخالص", "۳۴۲.۸ م", "+۶.۲٪", "green"],
            ["خط فروش فعال", "۱,۲۳۴ م", "+۴.۷٪", "yellow"],
            ["نرخ گردش موجودی", "۶.۸ بار", "+۲.۱٪", "pink"],
          ].map(([title, value, change, color]) => (

            <div
              key={title}
              className="rounded-2xl border border-white/[0.07] bg-[#101012] p-4"
            >

              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs text-zinc-500">
                  {title}
                </span>

                <span
                  className={`h-2 w-2 rounded-full ${
                    color === "cyan"
                      ? "bg-cyan-400"
                      : color === "green"
                      ? "bg-emerald-400"
                      : color === "yellow"
                      ? "bg-yellow-400"
                      : color === "pink"
                      ? "bg-pink-400"
                      : "bg-violet-500"
                  }`}
                />
              </div>

              <div className="text-xl font-bold">
                {value}
              </div>

              <div className="mt-2 flex items-center gap-2 text-[11px]">
                <span className="text-emerald-400">
                  {change}
                </span>

                <span className="text-zinc-600">
                  نسبت به ماه قبل
                </span>
              </div>

              <div className="mt-3 h-5">

                <svg
                  viewBox="0 0 160 25"
                  className="h-full w-full"
                >
                  <path
                    d="M0 18 C20 13 25 19 42 14 S70 7 82 13 S110 18 125 9 S145 12 160 4"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    className={
                      color === "cyan"
                        ? "text-cyan-400"
                        : color === "green"
                        ? "text-emerald-400"
                        : color === "yellow"
                        ? "text-yellow-400"
                        : color === "pink"
                        ? "text-pink-400"
                        : "text-violet-400"
                    }
                  />
                </svg>

              </div>

            </div>

          ))}

        </section>

        {/* MAIN GRID */}
        <section className="grid grid-cols-12 gap-5">

          {/* SALES */}
          <div className="col-span-12 rounded-2xl border border-white/[0.07] bg-[#101012] p-6 xl:col-span-8">

            <div className="mb-7 flex items-start justify-between">

              <div>
                <h2 className="text-lg font-bold">
                  تحلیل فروش و بازاریابی
                </h2>

                <p className="mt-1 text-xs text-zinc-600">
                  روند فروش، هدف و پیش‌بینی عملکرد
                </p>
              </div>

              <div className="flex gap-2 text-[11px]">

                <span className="rounded-lg bg-violet-500/10 px-3 py-2 text-violet-300">
                  این ماه
                </span>

                <span className="rounded-lg bg-white/[0.03] px-3 py-2 text-zinc-500">
                  ۱۲ ماه
                </span>

              </div>

            </div>

            <div className="relative h-[310px]">

              <div className="absolute inset-0 flex flex-col justify-between">

                {[0, 1, 2, 3, 4].map((x) => (
                  <div
                    key={x}
                    className="border-t border-white/[0.045]"
                  />
                ))}

              </div>

              <svg
                viewBox="0 0 900 300"
                preserveAspectRatio="none"
                className="absolute inset-0 h-full w-full"
              >

                <path
                  d="M0 70 L80 95 L160 82 L240 130 L320 115 L400 150 L480 138 L560 175 L640 158 L720 205 L800 180 L900 145"
                  fill="none"
                  stroke="#8b5cf6"
                  strokeWidth="4"
                />

                <path
                  d="M0 85 L80 105 L160 98 L240 120 L320 128 L400 142 L480 155 L560 168 L640 177 L720 185 L800 190 L900 178"
                  fill="none"
                  stroke="#22d3ee"
                  strokeWidth="3"
                  strokeDasharray="7 8"
                />

              </svg>

              <div className="absolute bottom-0 left-0 right-0 flex justify-between text-[10px] text-zinc-600">

                {months.map((month) => (
                  <span key={month}>
                    {month}
                  </span>
                ))}

              </div>

            </div>

          </div>

          {/* CRM */}
          <div className="col-span-12 rounded-2xl border border-white/[0.07] bg-[#101012] p-6 xl:col-span-4">

            <div className="mb-6 flex items-center justify-between">

              <h2 className="font-bold">
                سلامت مشتریان و CRM
              </h2>

              <span className="text-pink-400">
                ♡
              </span>

            </div>

            <div className="rounded-xl border border-white/[0.06] bg-[#0b0b0d] p-5">

              <div className="text-xs text-zinc-500">
                شاخص رضایت مشتری (NPS)
              </div>

              <div className="mt-2 flex items-end gap-2">

                <span className="text-4xl font-bold">
                  ۷۲
                </span>

                <span className="mb-1 text-xs text-emerald-400">
                  +۶ نسبت به فصل قبل
                </span>

              </div>

              <div className="mt-5 h-3 overflow-hidden rounded-full bg-red-500">

                <div className="h-full w-[72%] bg-gradient-to-l from-emerald-400 via-yellow-400 to-red-500" />

              </div>

              <div className="mt-2 flex justify-between text-[10px] text-zinc-600">

                <span>منتقدان</span>
                <span>خنثی</span>
                <span>وفاداران</span>

              </div>

            </div>

            <div className="mt-4 grid grid-cols-2 gap-3">

              <Metric title="مشتریان فعال" value="۱,۲۸۴" />
              <Metric title="نرخ ریزش" value="۳.۸٪" green />
              <Metric title="مشتریان جدید" value="۸۴" />
              <Metric title="ارزش متوسط خرید" value="۶.۴ م" />

            </div>

          </div>

          {/* AI */}
          <div className="col-span-12 rounded-2xl border border-violet-900/30 bg-[#101012] p-6 xl:col-span-4">

            <div className="mb-5 flex items-center gap-3">

              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600/15 text-violet-400">
                ✦
              </div>

              <div>

                <h2 className="font-bold">
                  ایجنت خودمختار هوش مصنوعی
                </h2>

                <p className="text-[10px] text-emerald-400">
                  ● در حال فعالیت زنده
                </p>

              </div>

            </div>

            <div className="space-y-3">

              {activities.map(([text, time, color]) => (

                <div
                  key={text}
                  className="flex gap-3 rounded-xl border border-white/[0.05] bg-[#0b0b0d] p-3"
                >

                  <div
                    className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                      color === "green"
                        ? "bg-emerald-400"
                        : color === "purple"
                        ? "bg-violet-400"
                        : color === "pink"
                        ? "bg-pink-400"
                        : color === "blue"
                        ? "bg-blue-400"
                        : "bg-yellow-400"
                    }`}
                  />

                  <div>

                    <div className="text-xs text-zinc-300">
                      {text}
                    </div>

                    <div className="mt-1 text-[10px] text-zinc-600">
                      {time}
                    </div>

                  </div>

                </div>

              ))}

            </div>

          </div>

          {/* SALES PEOPLE */}
          <div className="col-span-12 rounded-2xl border border-white/[0.07] bg-[#101012] p-6 xl:col-span-4">

            <div className="mb-5 flex items-center justify-between">

              <h2 className="font-bold">
                برترین کارشناسان فروش
              </h2>

              <span className="text-yellow-400">
                ♙
              </span>

            </div>

            <div className="space-y-4">

              {salesPeople.map(([name, value, unit], index) => (

                <div
                  key={name}
                  className="flex items-center justify-between rounded-xl border border-white/[0.05] px-4 py-3"
                >

                  <div className="flex items-center gap-3">

                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-violet-500/20 text-xs text-violet-300">
                      {index + 1}
                    </span>

                    <span className="text-sm">
                      {name}
                    </span>

                  </div>

                  <span className="text-xs text-zinc-400">
                    {value} {unit}
                  </span>

                </div>

              ))}

            </div>

          </div>

          {/* INVENTORY */}
          <div className="col-span-12 rounded-2xl border border-white/[0.07] bg-[#101012] p-6 xl:col-span-4">

            <div className="mb-5 flex items-center justify-between">

              <h2 className="font-bold">
                انبار و زنجیره تأمین
              </h2>

              <span className="rounded-lg bg-red-500/10 px-3 py-2 text-[10px] text-red-400">
                ۳ هشدار
              </span>

            </div>

            <div className="space-y-4">

              {inventory.map(([name, code, value, color]) => (

                <div key={name}>

                  <div className="mb-2 flex justify-between text-xs">

                    <span className="text-zinc-300">
                      {name}
                      <span className="text-zinc-700">
                        {" "}• {code}
                      </span>
                    </span>

                    <span className="text-zinc-600">
                      ×{value}
                    </span>

                  </div>

                  <div className="h-2 overflow-hidden rounded-full bg-zinc-800">

                    <div
                      style={{ width: `${value}%` }}
                      className={`h-full rounded-full ${
                        color === "green"
                          ? "bg-emerald-400"
                          : color === "pink"
                          ? "bg-pink-400"
                          : "bg-yellow-400"
                      }`}
                    />

                  </div>

                </div>

              ))}

            </div>

          </div>

          {/* CASH FLOW */}
          <div className="col-span-12 rounded-2xl border border-white/[0.07] bg-[#101012] p-6 xl:col-span-4">

            <div className="mb-5 flex items-center justify-between">

              <div>

                <h2 className="font-bold">
                  جریان نقدی
                </h2>

                <p className="mt-1 text-[10px] text-zinc-600">
                  وضعیت دریافت و پرداخت
                </p>

              </div>

              <span className="text-emerald-400">
                ↗
              </span>

            </div>

            <div className="mb-5 text-3xl font-bold">
              ۱۸۹.۴
              <span className="text-sm text-zinc-600">
                {" "}م تومان
              </span>
            </div>

            <div className="flex h-28 items-end gap-2">

              {[35, 50, 42, 68, 54, 80, 64, 91, 73, 86, 78, 95].map(
                (height, index) => (

                  <div
                    key={index}
                    style={{ height: `${height}%` }}
                    className="flex-1 rounded-t-md bg-gradient-to-t from-violet-700/40 to-cyan-400/70"
                  />

                )
              )}

            </div>

          </div>

        </section>

        {/* AI ASSISTANT */}
        <section className="mt-5 flex items-center gap-4 rounded-2xl border border-white/[0.07] bg-[#101012] p-4">

          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-violet-600/15 text-violet-400">
            ✦
          </div>

          <div className="flex-1">

            <div className="text-sm font-medium">
              دستیار هوشمند Kiarad
            </div>

            <div className="text-[10px] text-zinc-600">
              هر چیزی درباره فروش، مشتری، انبار یا مالی بپرسید.
            </div>

          </div>

          <input
            className="hidden h-11 max-w-xl flex-1 rounded-xl border border-white/[0.07] bg-[#0b0b0d] px-4 text-sm outline-none placeholder:text-zinc-700 focus:border-violet-500/50 md:block"
            placeholder="مثلاً فروش این ماه چقدر بوده؟"
          />

          <button className="rounded-xl bg-violet-600 px-6 py-3 text-sm font-medium hover:bg-violet-500">
            پرسش
          </button>

        </section>

        <footer className="py-7 text-center text-[10px] text-zinc-700">
          Kiarad BI • Business Intelligence Platform
        </footer>

      </div>
    </main>
  );
}

function Metric({
  title,
  value,
  green = false,
}: {
  title: string;
  value: string;
  green?: boolean;
}) {
  return (
    <div className="rounded-xl border border-white/[0.06] bg-[#0b0b0d] p-4">

      <div className="text-[10px] text-zinc-600">
        {title}
      </div>

      <div
        className={`mt-2 text-xl font-bold ${
          green ? "text-emerald-400" : "text-white"
        }`}
      >
        {value}
      </div>

    </div>
  );
}