"""Legacy Digikala client. Importing this module never writes credentials or calls the network."""
import json
import os
from pathlib import Path

import requests

BASE_URL = "https://seller.digikala.com/open-api/v1"
TOKENS_PATH = Path(__file__).resolve().parent / "secrets" / "digikala_tokens.json"


class DigikalaProductCreationUnavailable(RuntimeError):
    """The current Seller Open API v1 does not expose product creation."""


class DigikalaClient:
    def __init__(self, tokens_path=TOKENS_PATH):
        self.tokens_path = Path(tokens_path)
        self.tokens = self._load_tokens()

    def _load_tokens(self):
        if not self.tokens_path.is_file():
            raise FileNotFoundError("Digikala credentials are not configured")
        # The PowerShell sync task writes this file as utf8 with BOM.
        with self.tokens_path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)

    def _save_tokens(self):
        self.tokens_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.tokens_path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(self.tokens, handle, ensure_ascii=False)
        os.replace(temporary, self.tokens_path)

    def refresh_access_token(self):
        refresh = self.tokens.get("refresh_token")
        if not refresh:
            raise ValueError("Digikala refresh token is missing")
        response = requests.post(
            f"{BASE_URL}/auth/refresh-token",
            json={"refresh_token": refresh}, timeout=20, allow_redirects=False,
        )
        response.raise_for_status()
        data = response.json().get("data", response.json())
        self.tokens["access_token"] = data["access_token"]
        if data.get("refresh_token"):
            self.tokens["refresh_token"] = data["refresh_token"]
        self._save_tokens()
        return self.tokens["access_token"]

    def request(self, method, endpoint, params=None, json_data=None):
        url = f"{BASE_URL}/{endpoint.lstrip('/')}"
        token = self.tokens.get("access_token")
        if not token:
            raise ValueError("Digikala access token is missing")
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json",
                  "User-Agent": "DigikalaTrustedBot/SelfToken/1061297"}
        response = requests.request(method, url, headers=headers, params=params, json=json_data, timeout=25, allow_redirects=False)
        if response.status_code == 401:
            headers["Authorization"] = f"Bearer {self.refresh_access_token()}"
            response = requests.request(method, url, headers=headers, params=params, json=json_data, timeout=25, allow_redirects=False)
        return response

    def get_profile(self):
        return self.request("GET", "/profile")

    def get_orders_statistics(self):
        return self.request("GET", "/orders/statistics")

    def get_orders(self, page=1, size=30):
        return self.request("GET", "/orders", params={"page": page, "size": size})

    def get_variants(self, page=1, size=30):
        return self.request("GET", "/variants", params={"page": page, "size": size})

    def update_stock(self, variant_id, stock_count):
        return self.request("PATCH", f"/variants/{variant_id}/seller-stock", json_data={"count": stock_count})

    def update_price(self, variant_id, price):
        return self.request("PATCH", "/variants/selling-price", json_data={"variant_id": variant_id, "selling_price": price})

    def get_category_tree(self):
        """Confirmed working (probed 2026-11-07: GET /categories/tree -> 200)."""
        return self.request("GET", "/categories/tree")

    def create_product(self, payload: dict):
        """Fail closed: Seller Open API v1 has no confirmed product-create route.

        Product creation must be completed manually in Seller Center. Once a
        documented endpoint is published and verified, replace this guard.
        """
        raise DigikalaProductCreationUnavailable(
            "Digikala Seller Open API v1 does not currently support product creation; "
            "create the listing in Seller Center and map its variant afterwards."
        )
