"use client";

import { useEffect, useState } from "react";

const API = "http://127.0.0.1:8000";

type CEO = {
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

type Staff = {
  id: number;
  name: string;
  sales_amount: number;
  target: number;
  sales_count: number;
  achievement_percent: number;
  remaining: number;
};

export default function ManagementPage() {
  const [ceo, setCeo] = useState<CEO | null>(null);
  const [staff, setStaff] = useState<Staff[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const ceoRes = await fetch(`${API}/dashboard/ceo`);
        const ceoData = await ceoRes.json();

        const staffRes = await fetch(`${API}/staff/performance`);
        const staffData = await staffRes.json();

        setCeo(ceoData);
        setStaff(staffData.staff || []);

      } catch (error) {
        console.log(error);
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, []);


  if (loading) {
    return (
      <div className="p-10 text-xl">
        در حال دریافت اطلاعات...
      </div>
    );
  }


  if (!ceo) {
    return (
      <div className="p-10 text-xl">
        اطلاعات دریافت نشد
      </div>
    );
  }


  const money = (value: number) =>
    value.toLocaleString("fa-IR");


  return (
    <main className="p-8" dir="rtl">


      <h1 className="text-3xl font-bold mb-8">
        داشبورد مدیریت کیاراد BI
      </h1>



      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">


        <Card
          title="فروش کل"
          value={money(ceo.sales.amount)}
        />


        <Card
          title="تعداد فاکتور"
          value={money(ceo.sales.count)}
        />


        <Card
          title="تعداد مشتری"
          value={money(ceo.customers)}
        />


        <Card
          title="وصولی"
          value={money(ceo.payments)}
        />


        <Card
          title="هدف فروش"
          value={money(ceo.target)}
        />


        <Card
          title="تحقق هدف"
          value={`${ceo.achievement}%`}
        />


      </div>



      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-5">


        <Card
          title="بدهی کل مشتریان"
          value={money(ceo.debt)}
        />


        <Card
          title="وضعیت فروش"
          value={
            ceo.achievement < 50
              ? "نیاز به پیگیری"
              : "مطلوب"
          }
        />


      </div>




      <section className="mt-10">


        <h2 className="text-2xl font-bold mb-5">
          عملکرد فروشندگان
        </h2>


        <div className="overflow-x-auto">


          <table className="w-full border">


            <thead>

              <tr className="border bg-gray-100">

                <th className="p-3">
                  نام
                </th>

                <th className="p-3">
                  فروش
                </th>

                <th className="p-3">
                  تعداد فاکتور
                </th>

                <th className="p-3">
                  هدف
                </th>

                <th className="p-3">
                  تحقق
                </th>

                <th className="p-3">
                  مانده
                </th>

              </tr>

            </thead>



            <tbody>

              {staff.map((person) => (

                <tr
                  key={person.id}
                  className="border text-center"
                >

                  <td className="p-3">
                    {person.name}
                  </td>


                  <td className="p-3">
                    {money(person.sales_amount)}
                  </td>


                  <td className="p-3">
                    {person.sales_count}
                  </td>


                  <td className="p-3">
                    {money(person.target)}
                  </td>


                  <td className="p-3">
                    {person.achievement_percent}%
                  </td>


                  <td className="p-3">
                    {money(person.remaining)}
                  </td>


                </tr>

              ))}


            </tbody>


          </table>


        </div>


      </section>


    </main>
  );
}



function Card(
  {
    title,
    value
  }:
  {
    title:string;
    value:string;
  }
) {

  return (

    <div className="rounded-xl border p-6 shadow-sm">

      <div className="text-gray-600 mb-3">
        {title}
      </div>

      <div className="text-2xl font-bold">
        {value}
      </div>

    </div>

  );

}