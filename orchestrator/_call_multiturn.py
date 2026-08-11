import json, subprocess, urllib.request

URL = "https://it-triage-orchestrator-487169635000.us-east1.run.app/chat"
SESSION = "demo-session-5turn"   # same session id across all turns = shared memory

TURNS = [
    "Hi, my user id is u_1001. My laptop asset AST-100 keeps freezing.",
    "What was the ticket id you just opened?",
    "Also, I can't connect to the VPN.",
    "Remind me — which asset did I first ask about?",
    "And what temporary VPN password did you give me?",
]

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

tok = token()
for i, msg in enumerate(TURNS, 1):
    print(f"\n=== TURN {i} — user: {msg}")
    data = ask(msg, tok)
    print("agents:", data["agents_called"])
    print("reply :", data["reply"])