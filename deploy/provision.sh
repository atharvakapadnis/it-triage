#!/usr/bin/env bash
# Provision + deploy the IT Support Triage system to Google Cloud Run from scratch.
#
# Creates two IAM-locked Cloud Run services:
#   it-triage-mcp           - the MCP tool server
#   it-triage-orchestrator  - the ADK multi-agent orchestrator
#
# PREREQUISITES (one-time, not scriptable):
#   1. Install the gcloud CLI, then:  gcloud auth login
#   2. Create a GCP project and LINK A BILLING ACCOUNT (Console > Billing).
#   3. Point this script at your project:  export PROJECT_ID=your-project-id
#      (falls back to your current gcloud project if unset)
#
# Then from the repo root:  bash deploy/provision.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${REGION:-us-east1}"
ORCH_SA="it-triage-orch@${PROJECT_ID}.iam.gserviceaccount.com"

echo "Deploying to project: $PROJECT_ID   region: $REGION"
gcloud config set project "$PROJECT_ID"

# 1. Enable required APIs
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com

# 2. First-project IAM: let Cloud Build's default SA fetch source + build
#    (a brand-new project lacks these -> the first source deploy 403s without them)
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for ROLE in roles/storage.objectViewer roles/cloudbuild.builds.builder; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${COMPUTE_SA}" --role="$ROLE" --condition=None
done

# Pre-create the source-deploy Artifact Registry repo so deploys run non-interactively
gcloud artifacts repositories create cloud-run-source-deploy \
  --repository-format=docker --location="$REGION" \
  --description="Cloud Run source deploys" 2>/dev/null || true

# 3. Deploy the MCP server, then remove public access (lock it to IAM)
gcloud run deploy it-triage-mcp \
  --source mcp_server --region "$REGION" --allow-unauthenticated --quiet
gcloud run services remove-iam-policy-binding it-triage-mcp --region "$REGION" \
  --member="allUsers" --role="roles/run.invoker" 2>/dev/null || true
MCP_URL="$(gcloud run services describe it-triage-mcp --region "$REGION" --format='value(status.url)')/mcp"
echo "MCP server (locked): $MCP_URL"

# 4. Dedicated SA for the orchestrator + least-privilege grants
gcloud iam service-accounts create it-triage-orch \
  --display-name="IT Triage Orchestrator" 2>/dev/null || true
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${ORCH_SA}" --role="roles/aiplatform.user" --condition=None
gcloud run services add-iam-policy-binding it-triage-mcp --region "$REGION" \
  --member="serviceAccount:${ORCH_SA}" --role="roles/run.invoker"

# 5. Deploy the orchestrator (IAM-locked, runs AS the dedicated SA, MCP URL injected)
gcloud run deploy it-triage-orchestrator \
  --source orchestrator --region "$REGION" \
  --no-allow-unauthenticated \
  --service-account="$ORCH_SA" \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},MCP_SERVER_URL=${MCP_URL}" \
  --max-instances=1 --quiet

echo "Orchestrator (locked): $(gcloud run services describe it-triage-orchestrator --region "$REGION" --format='value(status.url)')"