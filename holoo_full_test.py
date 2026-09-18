import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("HOLO_API_URL")
USERNAME = os.getenv("HOLO_USERNAME", "web")
PASSWORD = os.getenv("HOLO_PASSWORD", "MQ==")

OUTPUT = "holoo_export_test.json"


def login():
    print("=== LOGIN ===")

    url = BASE_URL + "/Login"

    data = {
        "userinfo": {
            "username": USERNAME,
            "userpass": PASSWORD,
            "dbname": "Holoo2"
        }
    }

    r = requests.post(
        url,
        json=data,
        timeout=30
    )

    print("Login Status:", r.status_code)

    result = r.json()

    if not result["Login"]["State"]:
        raise Exception("Login Failed")

    token = result["Login"]["Token"]

    print("TOKEN OK")

    return token


def get_data(endpoint, token):
    print("\nGET:", endpoint)

    r = requests.get(
        BASE_URL + endpoint,
        headers={
            "Authorization": token
        },
        timeout=120
    )

    print("Status:", r.status_code)

    try:
        data = r.json()
        print("Count:", len(data.get(endpoint.replace("/",""), [])))
        return data

    except Exception:
        print(r.text[:500])
        return {}


def main():

    result = {
        "time": str(datetime.now()),
        "customers": {},
        "products": {}
    }

    token = login()

    result["customers"] = get_data(
        "/Customer",
        token
    )

    result["products"] = get_data(
        "/Product",
        token
    )

    with open(
        OUTPUT,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("\n================")
    print("DONE")
    print("Saved:", OUTPUT)


if __name__ == "__main__":
    main()

