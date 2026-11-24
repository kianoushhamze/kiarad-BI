"use client";

import { useEffect, useRef, useState, type ChangeEvent, type FocusEvent } from "react";
import { formatJalaliDateInput, jalaliDateInputToIso } from "../lib/iran-date";

type IranDateInputProps = {
  name?: string;
  value?: string;
  defaultValue?: string;
  onChange?: (isoDate: string) => void;
  min?: string;
  max?: string;
  required?: boolean;
  disabled?: boolean;
  className?: string;
  style?: React.CSSProperties;
  "aria-label"?: string;
};

function displayDate(value?: string): string {
  return value ? formatJalaliDateInput(value) : "";
}

export function IranDateInput({
  name,
  value,
  defaultValue,
  onChange,
  min,
  max,
  required,
  disabled,
  className,
  style,
  "aria-label": ariaLabel,
}: IranDateInputProps) {
  const isControlled = value !== undefined;
  const [rawValue, setRawValue] = useState(() => displayDate(isControlled ? value : defaultValue));
  const lastEmittedValue = useRef<string | undefined>(undefined);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isControlled && value !== lastEmittedValue.current) {
      setRawValue(displayDate(value));
      lastEmittedValue.current = value;
    }
  }, [isControlled, value]);

  useEffect(() => {
    const form = inputRef.current?.form;
    if (!form || isControlled) return;
    const reset = () => setRawValue(displayDate(defaultValue));
    form.addEventListener("reset", reset);
    return () => form.removeEventListener("reset", reset);
  }, [defaultValue, isControlled]);

  const validate = (event: FocusEvent<HTMLInputElement>, raw: string) => {
    const isoDate = jalaliDateInputToIso(raw);
    let message = "";
    if (raw && !isoDate) message = "تاریخ شمسی معتبر وارد کنید؛ نمونه: ۱۴۰۵/۰۷/۲۶";
    else if (isoDate && min && isoDate < min) message = `تاریخ باید از ${formatJalaliDateInput(min)} زودتر نباشد.`;
    else if (isoDate && max && isoDate > max) message = `تاریخ باید از ${formatJalaliDateInput(max)} دیرتر نباشد.`;
    event.currentTarget.setCustomValidity(message);
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const next = event.currentTarget.value;
    setRawValue(next);
    event.currentTarget.setCustomValidity("");
    const isoDate = jalaliDateInputToIso(next);
    lastEmittedValue.current = isoDate ?? "";
    onChange?.(lastEmittedValue.current);
  };

  const handleBlur = (event: FocusEvent<HTMLInputElement>) => validate(event, rawValue);
  const isoValue = jalaliDateInputToIso(rawValue) ?? "";

  return <>
    {name && <input type="hidden" name={name} value={isControlled ? value ?? "" : isoValue} />}
    <input
      type="text"
      inputMode="numeric"
      dir="ltr"
      lang="fa-IR"
      autoComplete="off"
      placeholder="سال/ماه/روز شمسی"
      aria-label={ariaLabel}
      aria-invalid={Boolean(rawValue && !isoValue)}
      maxLength={10}
      required={required}
      disabled={disabled}
      className={className}
      style={style}
      ref={inputRef}
      value={rawValue}
      onChange={handleChange}
      onBlur={handleBlur}
    />
  </>;
}
