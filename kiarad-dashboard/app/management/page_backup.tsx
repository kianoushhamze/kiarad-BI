"use client";

import { useEffect, useState } from "react";

const API_URL = "http://127.0.0.1:8000";

type CEOData = {
  sales: {
    amount: number;
    count: number;
  };
  payments: number;
  customers: number;
  target: number;
  achievement: number;
  debt: number;
};

export default function ManagementPage() {
  const [data, setData] = useState<CEOData | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/dashboard/ceo`)
      .then((res) => res.json())
      .then((result) => {
        setData(result);
      });
  }, []);

  if (!data) {
    return (
      <div className="p-10 text-xl">
        در حال دریافت اطلاعات...
      </div>
    );
  }

  return (
    <main className="p-8">

      <h1 className="text-3xl font-bold mb-8">
        داشبورد مدیریت کیاراد BI
      </h1>


      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">


        <div className="rounded-xl border p-6">
          <h2>فروش کل</h2>
          <p className="text-2xl font-bold">
            {data.sales.amount.toLocaleString()}
          </p>
        </div>


        <div className="rounded-xl border p-6">
          <h2>تعداد فاکتور</h2>
          <p className="text-2xl font-bold">
            {data.sales.count}
          </p>
        </div>


        <div className="rounded-xl border p-6">
          <h2>مشتریان</h2>
          <p className="text-2xl font-bold">
            {data.customers}
          </p>
        </div>


        <div className="rounded-xl border p-6">
          <h2>وصولی</h2>
          <p className="text-2xl font-bold">
            {data.payments.toLocaleString()}
          </p>
        </div>


        <div className="rounded-xl border p-6">
          <h2>هدف فروش</h2>
          <p className="text-2xl font-bold">
            {data.target.toLocaleString()}
          </p>
        </div>


        <div className="rounded-xl border p-6">
          <h2>تحقق هدف</h2>
          <p className="text-2xl font-bold">
            {data.achievement}%
          </p>
        </div>


      </div>


      <div className="mt-8 rounded-xl border p-6">

        <h2 className="text-xl font-bold">
          مانده مطالبات
        </h2>

        <p className="text-3xl font-bold mt-3">
          {data.debt.toLocaleString()}
        </p>

      </div>


    </main>
  );
}