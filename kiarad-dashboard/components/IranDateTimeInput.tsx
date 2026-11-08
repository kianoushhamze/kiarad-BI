"use client";

import { useEffect, useRef, useState, type ChangeEvent, type FocusEvent } from "react";
import { formatIranDateTimeInput, iranDateTimeInputToIso } from "../lib/iran-date";

type IranDateTimeInputProps = {
  name: string;
  minDate?: string;
  required?: boolean;
  className?: string;
};

export function IranDateTimeInput({ name, minDate, required, className }: IranDateTimeInputProps) {
  const [rawValue, setRawValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const isoValue = iranDateTimeInputToIso(rawValue) ?? "";

  useEffect(() => {
    const form = inputRef.current?.form;
    if (!form) return;
    const reset = () => setRawValue("");
    form.addEventListener("reset", reset);
    return () => form.removeEventListener("reset", reset);
  }, []);

  const validate = (event: FocusEvent<HTMLInputElement>, raw: string) => {
    const isoDateTime = iranDateTimeInputToIso(raw);
    const selectedDate = isoDateTime ? formatIranDateTimeInput(isoDateTime).slice(0, 10) : "";
    let message = "";
    if (raw && !isoDateTime) message = "تاریخ و ساعت شمسی معتبر وارد کنید؛ نمونه: ۱۴۰۵/۰۷/۲۶ ۱۴:۳۰";
    else if (selectedDate && minDate && isoDateTime && new Date(isoDateTime) < new Date(`${minDate}T00:00:00+03:30`)) {
      message = `تاریخ باید از ${formatIranDateTimeInput(`${minDate}T00:00:00+03:30`).slice(0, 10)} زودتر نباشد.`;
    }
    event.currentTarget.setCustomValidity(message);
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    setRawValue(event.currentTarget.value);
    event.currentTarget.setCustomValidity("");
  };

  return <>
    <input type="hidden" name={name} value={isoValue} />
    <input
      type="text"
      inputMode="numeric"
      dir="ltr"
      lang="fa-IR"
      autoComplete="off"
      placeholder="سال/ماه/روز شمسی  ساعت:دقیقه"
      aria-label="تاریخ و ساعت شمسی به وقت تهران"
      aria-invalid={Boolean(rawValue && !isoValue)}
      maxLength={18}
      required={required}
      className={className}
      ref={inputRef}
      value={rawValue}
      onChange={handleChange}
      onBlur={(event) => validate(event, rawValue)}
    />
  </>;
}
