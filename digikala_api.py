import os
import json
import time
from datetime import datetime, timedelta
import requests

TOKENS_PATH = os.path.join("secrets", "digikala_tokens.json")
BASE_URL = "https://seller.digikala.com/open-api/v1"

class DigikalaClient:
    def __init__(self, tokens_path=TOKENS_PATH):
        self.tokens_path = tokens_path
        self.tokens = self._load_tokens()

    def _load_tokens(self):
        if not os.path.exists(self.tokens_path):
            raise FileNotFoundError(f"فایل توکن در مسیر {self.tokens_path} یافت نشد.")
        with open(self.tokens_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_tokens(self, tokens_data):
        self.tokens = tokens_data
        with open(self.tokens_path, "w", encoding="utf-8") as f:
            json.dump(tokens_data, f, ensure_ascii=False, indent=2)

    def get_access_token(self):
        # بررسی یا تمدید خودکار توکن
        return self.tokens.get("access_token")

    def refresh_access_token(self):
        """تمدید خودکار Access Token با استفاده از Refresh Token"""
        refresh_token = self.tokens.get("refresh_token")
        if not refresh_token:
            raise ValueError("Refresh Token یافت نشد.")

        url = f"{BASE_URL}/auth/refresh-token"
        payload = {"refresh_token": refresh_token}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        if resp.status_code in [200, 201]:
            data = resp.json().get("data", resp.json())
            self.tokens["access_token"] = data.get("access_token", self.tokens["access_token"])
            if "refresh_token" in data:
                self.tokens["refresh_token"] = data["refresh_token"]
            self._save_tokens(self.tokens)
            print("Access Token دیجی‌کالا با موفقیت تمدید شد.")
            return self.tokens["access_token"]
        else:
            raise Exception(f"خطا در تمدید توکن: {resp.text}")

    def request(self, method, endpoint, params=None, json_data=None):
        url = f"{BASE_URL}{endpoint}" if endpoint.startswith("/") else f"{BASE_URL}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.get_access_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        resp = requests.request(method, url, headers=headers, params=params, json=json_data, timeout=25)
        
        # در صورت انقضای توکن، یک‌بار تمدید و تلاش مجدد
        if resp.status_code == 401:
            headers["Authorization"] = f"Bearer {self.refresh_access_token()}"
            resp = requests.request(method, url, headers=headers, params=params, json=json_data, timeout=25)

        return resp

    # ۱. دریافت اطلاعات پروفایل و نام فروشگاه
    def get_profile(self):
        return self.request("GET", "/profile")

    # ۲. آمار سفارش‌ها
    def get_orders_statistics(self):
        return self.request("GET", "/orders/statistics")

    # ۳. لیست سفارش‌ها
    def get_orders(self, page=1, size=30):
        return self.request("GET", "/orders", params={"page": page, "size": size})

    # ۴. لیست تنوع کالاها و قیمت/موجودی
    def get_variants(self, page=1, size=30):
        return self.request("GET", "/variants", params={"page": page, "size": size})

    # ۵. به‌روزرسانی موجودی انبار کالا در دیجی‌کالا
    def update_stock(self, variant_id, stock_count):
        return self.request("PATCH", f"/variants/{variant_id}/seller-stock", json_data={"count": stock_count})

    # ۶. به‌روزرسانی قیمت فروش
    def update_price(self, variant_id, price):
        return self.request("PATCH", "/variants/selling-price", json_data={"variant_id": variant_id, "selling_price": price})

# ذخیره توکنی که هم‌اکنون از دیجی‌کالا دریافت شد
initial_tokens = {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzM4NCJ9.eyJ0b2tlbl9pZCI6MjM5NTUsInNlbGxlcl9pZCI6MTA2MTI5NywiY2xpZW50X2NvZGUiOiJUbWM1TjNwYVRFdGlTRVV2UTBjd1p6TnJibFozUVQwOSIsImV4cCI6MTc4OTI5MzY3MH0.pSmU7erGPSbLiOb8aMGWTqX-OIehZy602zXiqzmVHz5J8MWY4phm9XTeEb7XM_LN",
    "refresh_token": "mu4jgEVkvSwyLfb8HWu8Rlrl9YcFzdQiDTCBs1GnHHkprlEmGlRxjOLKGSv4BJzN",
    "seller_id": 1061297,
    "client_code": "Tmc5N3paTEtiSEUvQ0cwZzNrblZ3QT09"
}

with open(TOKENS_PATH, "w", encoding="utf-8") as f:
    json.dump(initial_tokens, f, ensure_ascii=False, indent=2)

print(" فایل توکن ذخیره شد. در حال ارسال اولین تست به دیجی‌کالا...")
client = DigikalaClient()

# تست خواندن پروفایل فروشگاه
# resp_profile = client.get_profile()
print(f"کد وضعیت پروفایل: {resp_profile.status_code}")
if resp_profile.status_code == 200:
    pdata = resp_profile.json().get("data", {})
    title = pdata.get("title") or pdata.get("seller_title") or pdata.get("name")
    print(f" نام فروشگاه دیجی‌کالا: {title}")

# تست خواندن آمار سفارش‌ها
resp_stats = client.get_orders_statistics()
print(f"کد وضعیت آمار سفارش‌ها: {resp_stats.status_code}")
if resp_stats.status_code == 200:
    print(f" آمار سفارش‌های دیجی‌کالا: {resp_stats.json().get('data', {})}")
