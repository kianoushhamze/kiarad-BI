import os
import sys
import base64
import json
import requests
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric import padding

KEY_PATH = os.path.join("secrets", "digikala_private.pem")
ENCRYPTED_B64 = """hXapvZ9jWqdvpfY00HQqBJCdnpwS+VM1GVr5Hc4bxtotjzSKatkd/5YeGAt2KPBuxq1/0fPJROcIALWUM3ySrcLzSHhIYfTp+WDlkVHGV1nYGhhPzCbgomngrpC8S2i6qrPgTtI851YaqvN0hLB5QgL8CAE0hSfcypAfqwUPwAozAb7JbtSWMBJCWEfqRosD3bqYVkv5FziNLw3FcIFZpmGeOijP3zz1Yhe4+0e/R+9AOlqX0c1vSAwhQJGiESOxRp5t17tUDX+V+uoNFTxwTb5OevXtVufOeWiOpwQwQd+wHdvk9fEhwycI5qS2CtsXLm+Uypj8/GGGDXGNtRuffcO4MOzUd4j2TcdnINQWhFMqcy+tpbxRheR9fgtzwh9ucOyYbakcZJdRUXpZWwBRXXigOoiA+L5RWg1kOBjhNsro7U8hzRv0BbHSnlU1gZIOmoeywYd2FpIvoxY+JCgVLlL22yrJwLqWfsUC762dyeJqDs4yfPeT9q+5iHPjFOJ49LCSmWS01wPJ6NnhXnDfFQHbf1EPineDbRSTMSUq4ieTMir+WwOujDRk7UGNoOVz9gXpPGMDCq/b+oQjrlhmM54NmaVky8eQhHK38086RpWgdResOIwL9hg3p+XxMgvmMSCP8gmLWV4i6AIFRcO9I91R7ueB54aCUC7OFdDMdag="""

def main():
    if not os.path.exists(KEY_PATH):
        print(f"خطا: فایل کلید در مسیر {KEY_PATH} یافت نشد!")
        return

    print("۱. خواندن کلید خصوصی و رمزگشایی...")
    with open(KEY_PATH, "rb") as f:
        private_key = load_pem_private_key(f.read(), password=None)

    raw_cipher = base64.b64decode(ENCRYPTED_B64.strip())
    decrypted_bytes = private_key.decrypt(raw_cipher, padding.PKCS1v15())
    decrypted_text = decrypted_bytes.decode('utf-8', errors='ignore').strip()
    print(f" کد با موفقیت رمزگشایی شد (طول: {len(decrypted_text)} کاراکتر)")

    print("۲. ارسال کد به سرور دیجی‌کالا با فیلد authorization_code...")
    url = "https://seller.digikala.com/open-api/v1/auth/token"
    payload = {"authorization_code": decrypted_text}
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        print(f"کد وضعیت پاسخ سرور: {resp.status_code}")
        data = resp.json()
        
        if resp.status_code in [200, 201] and data.get("status") in ["success", 200, None]:
            tokens = data.get("data", data)
            token_file = os.path.join("secrets", "digikala_tokens.json")
            with open(token_file, "w", encoding="utf-8") as tf:
                json.dump(tokens, tf, ensure_ascii=False, indent=2)
            print(f"\n توکن‌های دیجی‌کالا با موفقیت دریافت و در {token_file} ذخیره شدند!")
        else:
            print(f"پاسخ دیجی‌کالا: {data}")
    except Exception as e:
        print(f"خطا در ارسال درخواست: {e}")

if __name__ == "__main__":
    main()
