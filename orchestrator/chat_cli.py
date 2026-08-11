import json, subprocess, urllib.request, uuid

URL = "https://it-triage-orchestrator-487169635000.us-east1.run.app/chat"
SESSION = f"cli-{uuid.uuid4().hex[:8]}"   # one session for this whole CLI run

def token():
    return subprocess.check_output(
        ["gcloud", "auth", "print-identity-token"], shell=True
    ).decode().strip()

def ask(msg, tok):
    body = json.dumps({"session_id": SESSION, "message": msg}).encode()
    req = urllib.request.Request(
        URL, data=body,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

print(f"IT Triage — session {SESSION}. Type your message, or 'quit' to exit.\n")
tok = token()
while True:
    msg = input("you > ").strip()
    if msg.lower() in {"quit", "exit"}:
        break
    if not msg:
        continue
    data = ask(msg, tok)
    if data["agents_called"]:
        print("      [routed to:", ", ".join(data["agents_called"]) + "]")
    print("mimir >", data["reply"], "\n")