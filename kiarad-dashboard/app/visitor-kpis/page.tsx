import { redirect } from "next/navigation";

/** کارنامهٔ ویزیتورها اکنون تب «کارنامه ویزیتورها» در داشبورد مدیریت است. */
export default function VisitorKpiPage() {
  redirect("/management");
}
