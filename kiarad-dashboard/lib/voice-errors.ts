export function microphoneErrorMessage(reason: unknown): string {
  const name = typeof reason === "object" && reason !== null && "name" in reason
    ? String(reason.name) : "";
  switch (name) {
    case "NotAllowedError":
    case "PermissionDeniedError":
    case "SecurityError":
      return "مرورگر یا تنظیمات حریم خصوصی دستگاه دسترسی میکروفون را رد کرد. اگر اجازهٔ سایت فعال است، دسترسی خود مرورگر در تنظیمات سیستم را بررسی کنید. در مرورگر داخلی برنامه‌ها، نشانی همین صفحه را در اج یا کروم باز کنید و دوباره اجازه بدهید.";
    case "NotFoundError":
    case "DevicesNotFoundError":
      return "میکروفون فعالی پیدا نشد؛ اتصال میکروفون و دستگاه ورودی انتخاب‌شده را بررسی کنید یا فایل صوتی انتخاب کنید.";
    case "NotReadableError":
    case "TrackStartError":
      return "مرورگر نتوانست میکروفون را باز کند؛ ممکن است دستگاه در برنامهٔ دیگری مشغول باشد یا دسترسی آن در سیستم بسته باشد.";
    case "OverconstrainedError":
    case "ConstraintNotSatisfiedError":
      return "تنظیمات میکروفون انتخاب‌شده با ضبط سازگار نیست؛ دستگاه ورودی دیگری انتخاب کنید یا فایل صوتی بفرستید.";
    case "NotSupportedError":
      return "مرورگر قالب ضبط صوت را پشتیبانی نمی‌کند؛ مرورگر را به‌روز کنید، فایل صوتی انتخاب کنید یا گزارش را متنی بنویسید.";
    case "AbortError":
      return "شروع میکروفون توسط دستگاه یا مرورگر قطع شد؛ اتصال میکروفون را بررسی کنید و دوباره تلاش کنید.";
    case "TimeoutError":
      return "پاسخ درخواست میکروفون در زمان لازم نرسید. پنجرهٔ اجازه و تنظیمات دستگاه ورودی را بررسی کنید، سپس دوباره تلاش کنید.";
    default:
      return "شروع ضبط ممکن نشد؛ میکروفون و دستگاه ورودی مرورگر را بررسی کنید. می‌توانید فایل صوتی انتخاب کنید یا گزارش را متنی وارد کنید.";
  }
}
