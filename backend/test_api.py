import requests

URL = 'https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json'
HEADERS = {'User-Agent': 'Mozilla/5.0'}

def test(payload, desc):
    try:
        r = requests.post(URL, json=payload, headers=HEADERS) if payload else requests.get(URL, headers=HEADERS)
        # Try POST as JSON just in case, then GET
        if r.status_code != 200:
            r = requests.get(URL, params=payload, headers=HEADERS)
            
        data = r.json().get("data", {}).get("list", [])
        print(f"{desc}: Received {len(data)} rows.")
        if data:
            print(f"  -> Latest: {data[0]['issueNumber']}, Oldest: {data[-1]['issueNumber']}")
    except Exception as e:
        print(f"Failed {desc}: {e}")

print("--- Testing Standard GET ---")
test(None, "Default Request")

print("\n--- Testing GET Params ---")
test({'pageSize': 100, 'pageNo': 1}, "pageSize=100")
test({'pageSize': 20, 'pageNo': 5}, "pageNo=5")

print("\n--- Testing POST payload ---")
test({"pageSize": 50, "pageNo": 1, "gameId": 1}, "POST JSON Payload")
