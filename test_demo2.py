import requests
import json

# Test demo2 endpoint
url = "http://127.0.0.1:5000/quiz"
payload = {
    "email": "23f3004206@ds.study.iitm.ac.in",
    "secret": "dracarys",
    "url": "https://tds-llm-analysis.s-anand.net/demo2"
}

print("Testing /demo2 endpoint...")
print(f"Payload: {json.dumps(payload, indent=2)}")

response = requests.post(url, json=payload, timeout=180)
print(f"\nStatus: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")
