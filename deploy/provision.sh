#!/usr/bin/env bash
# Provision + deploy the IT Support Triage system to Google Cloud Run from scratch.
# Two services: it-triage-mcp (MCP tool server) + it-triage-orchestrator (ADK agents).
# Run from the repo root.
set -euo pipefail

# --- Config ----------------------------------------------------------------
PROJECT_ID="project-16523fba-2f2f-4c0c-b7e"
REGION="us-east1"
ORCH_SA="it-triage-orch@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud config set project "$PROJECT_ID"

# --- 1. Enable required APIs -----------------------------------------------
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com

# --- 2. First-project IAM: let Cloud Build fetch source + build ------------
# A brand-new project's Compute Engine default SA lacks these; granting them
# avoids the source-fetch 403 on the first `run deploy --source`.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for ROLE in roles/storage.objectViewer roles/cloudbuild.builds.builder; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${COMPUTE_SA}" --role="$ROLE" --condition=None
done

# --- 3. Deploy the MCP server, then lock it down ---------------------------
gcloud run deploy it-triage-mcp \
  --source mcp_server --region "$REGION" --allow-unauthenticated
gcloud run services remove-iam-policy-binding it-triage-mcp --region "$REGION" \
  --member="allUsers" --role="roles/run.invoker" || true
MCP_URL="$(gcloud run services describe it-triage-mcp --region "$REGION" --format='value(status.url)')/mcp"
echo "MCP server: $MCP_URL"

# --- 4. Dedicated SA for the orchestrator + least-privilege grants ---------
gcloud iam service-accounts create it-triage-orch \
  --display-name="IT Triage Orchestrator" || true
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${ORCH_SA}" --role="roles/aiplatform.user" --condition=None
gcloud run services add-iam-policy-binding it-triage-mcp --region "$REGION" \
  --member="serviceAccount:${ORCH_SA}" --role="roles/run.invoker"

# --- 5. Deploy the orchestrator (IAM-locked, runs as the dedicated SA) ------
gcloud run deploy it-triage-orchestrator \
  --source orchestrator --region "$REGION" \
  --no-allow-unauthenticated \
  --service-account="$ORCH_SA" \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},MCP_SERVER_URL=${MCP_URL}" \
  --max-instances=1

echo "Orchestrator:"
gcloud run services describe it-triage-orchestrator --region "$REGION" --format='value(status.url)'