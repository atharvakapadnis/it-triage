import json, subprocess, urllib.request

URL = "https://it-triage-orchestrator-487169635000.us-east1.run.app/chat"
MSG = "I can't connect to the VPN, and I also need a Figma license approved for design work."

token = subprocess.check_output(["gcloud", "auth", "print-identity-token"], shell=True).decode().strip()
body = json.dumps({"message": MSG}).encode()
req = urllib.request.Request(
    URL, data=body,
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    print("HTTP", resp.status)
    print(json.dumps(json.loads(resp.read()), indent=2))