import os
import requests
from dotenv import load_dotenv

load_dotenv()

HOLO_URL = os.getenv("HOLO_API_URL", "http://192.168.1.105:8080/TncHoloo/api").rstrip("/")


def login():
    url = f"{HOLO_URL}/Login"

    data = {
        "userinfo": {
            "username": os.getenv("HOLO_USERNAME", "web"),
            "userpass": os.getenv("HOLO_PASSWORD", "MQ=="),
            "dbname": "Holoo2"
        }
    }

    print("Connecting to Holo...")

    response = requests.post(
        url,
        json=data,
        timeout=60
    )

    print("Status:", response.status_code)

    response.raise_for_status()

    result = response.json()

    print("Login response:", result)

    return result["Login"]["Token"]


def get_customers(token):

    url = f"{HOLO_URL}/Customer"

    headers = {
        "Authorization": token
    }

    print("Getting customers...")

    response = requests.get(
        url,
        headers=headers,
        timeout=60
    )

    print("Customer status:", response.status_code)

    response.raise_for_status()

    return response.json()


if __name__ == "__main__":

    try:
        token = login()

        print("TOKEN OK")

        customers = get_customers(token)

        print("CUSTOMERS:")
        print(customers)

    except Exception as e:
        print("ERROR:")
        print(e)

