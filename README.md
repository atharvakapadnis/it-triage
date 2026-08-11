some-text-here# IT Support Triage — Multi-Agent Orchestration (Google ADK + MCP + GCP)

A production-shaped multi-agent system that triages plain-language IT support
requests. A root orchestrator classifies each request, routes it to one or more
specialist agents, each specialist does real work through tools exposed over a
separate MCP server, and the orchestrator synthesizes a single reply.

* **Repo:** https://github.com/atharvakapadnis/it-triage
* **Stack:** Google ADK (agents) · Model Context Protocol (tools) · Vertex AI
  `gemini-2.5-flash` · Google Cloud Run (two services) · GitHub Actions (CI)

---

## Architecture

See `architecture.png` for the system diagram.

### Why the agents are split this way

Three specialists, one per problem domain in the scenario — **access**
(account/VPN/drive), **hardware** (devices), **licensing** (software + approvals).
No more, no fewer: the assignment rewards a clean system over an inflated one, and
three domains is exactly what the routing logic needs.

Each specialist runs a realistic **diagnose → act** workflow with two tools rather
than one, because real IT triage is never a single call:

| Agent     | Diagnose                  | Act                        |
| --------- | ------------------------- | -------------------------- |
| access    | `check_user_access`       | `reset_vpn_credentials`    |
| hardware  | `get_asset_status`        | `open_hardware_ticket`     |
| licensing | `check_license_inventory` | `request_license_approval` |

This two-tool shape is also what makes failure handling *real* rather than a shrug
(see "Error handling" below).

### The key routing decision: agents-as-tools, not sub-agent transfer

ADK offers two multi-agent patterns. With **`sub_agents` + LLM transfer**, the root
hands control to a specialist, and whoever holds control at the end produces the
reply — which makes merging results from *two* specialists into one answer awkward.
With **`AgentTool`** (chosen here), the root *calls* each specialist as a tool,
receives its result, and **keeps control** — so it can call one specialist or two,
then synthesize a single coherent response.

This is what makes multi-agent fan-out genuine rather than faked: a request like
*"I can't connect to the VPN, and I need a Figma license approved"* causes the root
to invoke both `access_agent` and `licensing_agent`, then merge the VPN reset and
the license approval into one reply.

### MCP integration — and an important note

The MCP server is a **genuinely separate Cloud Run service**, spoken to over
streamable HTTP (the only transport Cloud Run supports). Tool calls cross the wire
to a different process with its own IAM boundary — the strongest form of the
"MCP must be separate" requirement.

One deliberate deviation worth calling out: this project does **not** use ADK's
`McpToolset` adapter. On the pinned ADK version, `McpToolset` mangled the MCP tool
schemas such that Gemini 2.5 dropped into code-mode and emitted
`MALFORMED_FUNCTION_CALL`. A direct `google-genai` probe confirmed Vertex and the
model were fine — the fault was isolated to the adapter's schema conversion. The
workaround is a thin async `FunctionTool` per tool (`_call_mcp`) that opens a real
streamable-HTTP MCP `ClientSession`, calls one tool, and returns its
`structuredContent`.

This is **not** mocking the MCP layer: every tool call is a real MCP session to the
separate server. Only the *client adapter* was swapped — the protocol, the
separation, and the over-the-wire calls are all real.

### Error handling

Tools return failures as **structured data**, never exceptions — e.g.
`get_asset_status("AST-404")` returns `{"status": "not_found", ...}` and
`request_license_approval("adobe_cc", ...)` returns `{"status": "denied", ...}`.
Because the failure is data the agent reasons over, the hardware agent responds to
`not_found` by **opening a fallback ticket** instead of dead-ending — failure
triggers a recovery action, not just a caught error.

---

## Running locally

Requires Python 3.12+ and the gcloud CLI.

### 1. venv + deps

```text
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate elsewhere
pip install -r mcp_server/requirements.txt
pip install -r orchestrator/requirements.txt
pip install -r tests/requirements.txt
```

### 2. Auth for Vertex (the agents call Gemini via Application Default Credentials)

```text
gcloud auth application-default login
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

### 3. Config: copy the template, set values (use the LOCAL MCP url for local dev)

`orchestrator/.env` → `MCP_SERVER_URL=http://127.0.0.1:8080/mcp`

```text
cp orchestrator/.env.example orchestrator/.env   # then edit
```

### 4. Terminal A — the MCP server

```text
python mcp_server/server.py
```

### 5. Terminal B — the orchestrator API

```text
python orchestrator/main.py
```

### Tests

```text
pytest -m "not integration"        # unit tests — fast, no LLM/network (the CI gate)
pytest -m integration              # routing tests — needs the local MCP server + Vertex
```

---

## Deploying to GCP

Prerequisites that can't be scripted: install the gcloud CLI, `gcloud auth login`,
create a project, and **link a billing account**.

```text
export PROJECT_ID=your-project-id        # or rely on your current gcloud project
bash deploy/provision.sh
```

`provision.sh` enables the required APIs, grants the first-project Cloud Build IAM,
deploys the MCP server (then removes public access so it's IAM-only), creates a
dedicated service account for the orchestrator with least-privilege grants
(`aiplatform.user` + `run.invoker` scoped to the MCP service), and deploys the
orchestrator locked to IAM with the MCP URL injected.

Every command in the script was executed during the actual deployment; the script
consolidates those verified commands into one reproducible run.

### Service-to-service auth

The MCP service requires `roles/run.invoker`. The orchestrator runs as a dedicated
service account holding that role **scoped to the MCP service only**, and mints a
Google ID token per MCP call (audience = the MCP base URL). No shared secrets, no
open endpoints — verified by an anonymous call returning `403` and a token-bearing
call reaching the service.

### Live services

* MCP server: `https://it-triage-mcp-487169635000.us-east1.run.app` (IAM-locked)
* Orchestrator: `https://it-triage-orchestrator-487169635000.us-east1.run.app` (IAM-locked)

Both are IAM-locked, so calls need an identity token, e.g.:

```text
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
-H "Content-Type: application/json" \
-d '{"message":"I cant connect to the VPN, and I need a Figma license approved."}' \
https://it-triage-orchestrator-487169635000.us-east1.run.app/chat
```

> These services stay up until [8/13/2026]. Teardown:
> `gcloud run services delete it-triage-mcp it-triage-orchestrator --region us-east1`

---

## Observability

Every MCP tool call flows through one chokepoint (`_call_mcp`), which emits
structured JSON logs (`mcp_tool_call` / `mcp_tool_result` with the tool name and
result `status`) — so the logs narrate which tool ran and whether it succeeded or
hit a failure mode. The `/chat` response also returns `agents_called`, showing which
specialists the root routed to. On Cloud Run both land in Cloud Logging.

---

## Known limitations & what I'd do with more time

* **In-memory sessions, single instance.** Conversation state uses ADK's
  `InMemorySessionService` with `--max-instances=1` for session affinity, which
  satisfies multi-turn persistence but doesn't survive scale-out or a cold restart.
  Production: a `DatabaseSessionService` or `VertexAiSessionService`.
* **Vertex quota on a fresh project.** A burst of agent calls can hit
  `429 RESOURCE_EXHAUSTED` on the default new-project quota (this can surface in the
  integration tests). Production: request a quota increase and add exponential-backoff
  retry on the model.
* **Per-call MCP session + token.** Each tool call opens a fresh MCP session and mints
  a fresh ID token — simple and correct, mildly wasteful. Could pool connections and
  cache the token until expiry.
* **Tool visibility in the response.** Because `AgentTool` encapsulates each
  specialist's internal events, leaf tool calls don't surface in the root's event
  stream, so `tools_called` in the response is empty by design; tool-level visibility
  is provided through logging instead.
* **gcloud script, not Terraform.** A documented, reproducible `provision.sh` is
  provided; Terraform would be the next step for declarative state.

---

## Design decisions, in brief

* ADK `LlmAgent` throughout; **agents-as-tools** for the root so it retains control to
  fan out and synthesize.
* MCP over streamable HTTP to a separate service — real protocol, real separation.
* Failures as structured status fields, so agents recover rather than crash.
* Typed Pydantic tool I/O, so MCP emits structured content and Gemini gets real schemas.
* Least-privilege IAM with a dedicated orchestrator service account.
* Two-tier tests: deterministic unit tests (CI) + on-demand integration tests (Vertex).