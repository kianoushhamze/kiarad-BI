import json
from digikala_api import DigikalaClient

client = DigikalaClient()
print("در حال دریافت و تحلیل ساختار کالاهای شما در دیجی‌کالا...")
resp = client.get_variants(page=1, size=10)

if resp.status_code == 200:
    data = resp.json().get("data", {})
    variants = data.get("items", []) or data.get("variants", [])
    print(f"\n تعداد کل کالاها/تنوع‌ها: {data.get('total', len(variants))}\n" + "=" * 60)
    
    for i, v in enumerate(variants, start=1):
        vid = v.get("id") or v.get("variant_id")
        title = v.get("title") or v.get("product_title") or (v.get("product", {}) if isinstance(v.get("product"), dict) else {}).get("title", "بدون عنوان")
        
        # استخراج ایمن قیمت و موجودی
        price = v.get("price")
        if isinstance(price, dict):
            price_val = price.get("selling_price") or price.get("current_price")
        else:
            price_val = price or v.get("selling_price")

        price_display = f"{int(price_val):,} ریال" if price_val is not None else "ثبت نشده"
        stock = v.get("seller_stock") if v.get("seller_stock") is not None else v.get("stock", "نامشخص")
        
        print(f"[{i}] کد تنوع (Variant ID): {vid}")
        print(f"    عنوان: {title}")
        print(f"    قیمت: {price_display} | موجودی شما در دیجی‌کالا: {stock}")
        print("-" * 60)
        
    # ذخیره نمونه کالاها جهت نگاشت خودکار با هلو
    with open("digikala_variants_sample.json", "w", encoding="utf-8") as f:
        json.dump(variants, f, ensure_ascii=False, indent=2)
    print("\n ساختار کامل کالاها برای هماهنگ‌سازی در digikala_variants_sample.json ذخیره شد.")
else:
    print(f"خطا در دریافت کالاها: {resp.text}")
