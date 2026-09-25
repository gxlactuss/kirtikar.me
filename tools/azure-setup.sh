#!/usr/bin/env bash
# One pass through DEPLOY.md's "First-time setup", steps 1-7, plus the budget
# alert from "Things that would bite later". Run it from the repository root
# after `az login`:
#
#   ./tools/azure-setup.sh
#
# Safe to re-run: every step checks for what it would create and skips it if
# it is already there, so a pass that dies halfway (a provider still
# registering, a role assignment racing a brand-new principal) is finished by
# simply running it again.
#
# The API keys are read from a hidden prompt, or from SARVAM_API_KEY and
# GEMINI_API_KEY if they are already exported. They go straight into the
# container app's secrets and nowhere else: not this repository, not a file,
# not the shell history.
#
# Overridable from the environment:
#   AZURE_SUBSCRIPTION  default f3849fe0-171c-4378-81ce-3c1769804ed0
#   ACR                 registry name, globally unique; default kirtikaracr
#   GH_REPO             default gxlactuss/kirtikar.me
#   AZURE_LOCATION      default uaenorth; must be allowed by the subscription's
#                       policy AND offer Container Apps (see DEPLOY.md)
#   BUDGET_EMAIL        who the budget alert mails; prompted for if unset
#   BUDGET_AMOUNT       default 5, in the subscription's billing currency
set -euo pipefail

SUB="${AZURE_SUBSCRIPTION:-f3849fe0-171c-4378-81ce-3c1769804ed0}"
RG=kirtikar-rg
LOC="${AZURE_LOCATION:-uaenorth}"
ENV_NAME=kirtikar-env
APP=kirtikar-api
ACR="${ACR:-kirtikaracr}"
REPO="${GH_REPO:-gxlactuss/kirtikar.me}"
DEPLOYER=kirtikar-deployer
PLACEHOLDER=mcr.microsoft.com/k8se/quickstart:latest
CORS='https://kirtikar.me,https://www.kirtikar.me,http://localhost:5173'

step() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
skip() { printf '   already done: %s\n' "$*"; }
die() { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

[ -f backend/Dockerfile ] || die "run this from the repository root"
command -v az >/dev/null || die "the Azure CLI is not installed (brew install azure-cli)"

# ---------------------------------------------------------------- account

step "Subscription"
az account show -o none 2>/dev/null || die "not signed in; run: az login"
az account set --subscription "$SUB"
state=$(az account show --query state -o tsv)
az account show --query '{name:name, state:state, user:user.name}' -o table
[ "$state" = Enabled ] || die "subscription is '$state', not Enabled. An expired trial cannot run Container Apps."
TENANT=$(az account show --query tenantId -o tsv)

az extension add --name containerapp --upgrade --only-show-errors

# ---------------------------------------------------------------- 1. providers

step "1. Resource providers"
for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.OperationalInsights; do
  if [ "$(az provider show -n "$ns" --query registrationState -o tsv)" = Registered ]; then
    skip "$ns"
  else
    echo "   registering $ns (can take a few minutes)"
    az provider register --namespace "$ns" --wait
  fi
done

# ---------------------------------------------------------------- 2. RG + ACR

step "2. Resource group and registry"
if az group show -n "$RG" -o none 2>/dev/null; then
  skip "$RG"
else
  az group create --name "$RG" --location "$LOC" -o none
fi

if az acr show -n "$ACR" -g "$RG" -o none 2>/dev/null; then
  skip "$ACR"
else
  available=$(az acr check-name -n "$ACR" --query nameAvailable -o tsv)
  [ "$available" = true ] || die "registry name '$ACR' is taken; rerun with ACR=<another name>"
  az acr create --resource-group "$RG" --name "$ACR" \
    --sku Basic --location "$LOC" --admin-enabled true -o none
fi

# ---------------------------------------------------------------- 3. environment

step "3. Container Apps environment"
if az containerapp env show -n "$ENV_NAME" -g "$RG" -o none 2>/dev/null; then
  skip "$ENV_NAME"
else
  # ConsumptionOnly, never the CLI's default of Express: an Express
  # environment cannot pull from a private registry at all (it rejects both
  # the admin password and a managed identity) and has no revision suffixes.
  az containerapp env create --name "$ENV_NAME" --resource-group "$RG" --location "$LOC" \
    --environment-mode ConsumptionOnly -o none
fi

# ---------------------------------------------------------------- 4 + 5. the app

step "4-5. Container app"
if az containerapp show -n "$APP" -g "$RG" -o none 2>/dev/null; then
  skip "$APP (keys are rotated with 'az containerapp secret set', see DEPLOY.md)"
else
  if [ -z "${SARVAM_API_KEY:-}" ]; then read -rsp "   SARVAM_API_KEY: " SARVAM_API_KEY; echo; fi
  if [ -z "${GEMINI_API_KEY:-}" ]; then read -rsp "   GEMINI_API_KEY: " GEMINI_API_KEY; echo; fi
  [ -n "$SARVAM_API_KEY" ] && [ -n "$GEMINI_API_KEY" ] || die "both keys are needed to create the app"

  ACR_USER=$(az acr credential show -n "$ACR" --query username -o tsv)
  ACR_PASS=$(az acr credential show -n "$ACR" --query 'passwords[0].value' -o tsv)

  # The image is built by the Deploy API workflow on GitHub's runners: Azure
  # for Students refuses ACR Tasks (TasksOperationsNotAllowed), so `az acr
  # build` is out, and building linux/amd64 on an Apple Silicon laptop is slow
  # at best. Until that workflow has pushed once, start from a placeholder.
  if az acr repository show -n "$ACR" --image "$APP:latest" -o none 2>/dev/null; then
    FIRST_IMAGE="$ACR.azurecr.io/$APP:latest"
  else
    FIRST_IMAGE=$PLACEHOLDER
  fi
  az containerapp create \
    --name "$APP" \
    --resource-group "$RG" \
    --environment "$ENV_NAME" \
    --image "$FIRST_IMAGE" \
    --registry-server "$ACR.azurecr.io" \
    --registry-username "$ACR_USER" \
    --registry-password "$ACR_PASS" \
    --target-port 7860 \
    --ingress external \
    --cpu 1 --memory 2Gi \
    --min-replicas 0 --max-replicas 1 \
    --secrets "sarvam-api-key=$SARVAM_API_KEY" "gemini-api-key=$GEMINI_API_KEY" \
    --env-vars \
      "CORS_ORIGINS=$CORS" \
      'SARVAM_API_KEY=secretref:sarvam-api-key' \
      'GEMINI_API_KEY=secretref:gemini-api-key' \
    -o none
  # `create` drops the registry block when the image is not from it (the
  # placeholder), and the first real deploy then fails to pull. Set it again.
  az containerapp registry set -n "$APP" -g "$RG" --server "$ACR.azurecr.io" \
    --username "$ACR_USER" --password "$ACR_PASS" -o none
  unset SARVAM_API_KEY GEMINI_API_KEY ACR_PASS
fi

mode=$(az containerapp env show -n "$ENV_NAME" -g "$RG" --query properties.environmentMode -o tsv)
[ "$mode" != Express ] || die "$ENV_NAME is an Express environment, which cannot pull from $ACR. Delete it and $APP and rerun."

FQDN=$(az containerapp show -n "$APP" -g "$RG" --query 'properties.configuration.ingress.fqdn' -o tsv)
API_BASE="https://$FQDN"
echo "   app URL: $API_BASE"

# ---------------------------------------------------------------- 6. deployer

step "6. GitHub Actions deployer (OIDC, no secret)"
APP_ID=$(az ad app list --display-name "$DEPLOYER" --query '[0].appId' -o tsv)
if [ -n "$APP_ID" ]; then
  skip "app registration $DEPLOYER ($APP_ID)"
else
  APP_ID=$(az ad app create --display-name "$DEPLOYER" --query appId -o tsv)
fi

if az ad sp show --id "$APP_ID" -o none 2>/dev/null; then
  skip "service principal"
else
  az ad sp create --id "$APP_ID" -o none
fi

# Newer and transferred repositories sign with immutable ids in the subject
# (repo:owner@123/name@456:...), and the match is exact, so ask GitHub for the
# prefix rather than assuming the plain repo:owner/name form.
PREFIX=$(gh api "repos/$REPO/actions/oidc/customization/sub" --jq '.sub_claim_prefix // empty' 2>/dev/null || true)
SUBJECT="${PREFIX:-repo:$REPO}:ref:refs/heads/main"
if az ad app federated-credential list --id "$APP_ID" --query "[?subject=='$SUBJECT'] | [0].name" -o tsv | grep -q .; then
  skip "federated credential for $SUBJECT"
else
  az ad app federated-credential create --id "$APP_ID" --parameters "{
    \"name\": \"github-main\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"$SUBJECT\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
fi

# A brand-new service principal takes a little while to be visible to role
# assignment, and fails with "principal does not exist" until it is.
assign() {
  local role=$1 scope=$2
  if [ -n "$(az role assignment list --assignee "$APP_ID" --role "$role" --scope "$scope" --query '[0].id' -o tsv 2>/dev/null)" ]; then
    skip "$role"
    return
  fi
  for attempt in 1 2 3 4 5 6; do
    az role assignment create --assignee "$APP_ID" --role "$role" --scope "$scope" -o none 2>/dev/null && return
    echo "   waiting for the new principal to propagate ($attempt/6)"
    sleep 15
  done
  die "could not assign $role; rerun this script in a minute"
}
assign Contributor "/subscriptions/$SUB/resourceGroups/$RG"
assign AcrPush "/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ContainerRegistry/registries/$ACR"

# ---------------------------------------------------------------- 7. repo variables

step "7. Repository variables on $REPO"
vars=(
  "AZURE_CLIENT_ID=$APP_ID"
  "AZURE_TENANT_ID=$TENANT"
  "AZURE_SUBSCRIPTION_ID=$SUB"
  "AZURE_REGISTRY=$ACR"
  "VITE_API_BASE=$API_BASE"
)
# Actions variables need admin on the repository, not just push. When this
# account does not have it, print the values for whoever does.
set_ok=true
if command -v gh >/dev/null; then
  for kv in "${vars[@]}"; do
    gh variable set "${kv%%=*}" --repo "$REPO" --body "${kv#*=}" 2>/dev/null || { set_ok=false; break; }
  done
else
  set_ok=false
fi
if $set_ok; then
  gh variable list --repo "$REPO"
else
  echo "   Could not set them from here (gh missing, or this account is not a repo admin)."
  echo "   Someone with admin on $REPO must add these under"
  echo "   Settings -> Secrets and variables -> Actions -> Variables:"
  for kv in "${vars[@]}"; do printf '     %-22s %s\n' "${kv%%=*}" "${kv#*=}"; done
fi

# ---------------------------------------------------------------- budget

step "Budget alert"
BUDGET=kirtikar-monthly
if az rest --method get \
  --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Consumption/budgets/$BUDGET?api-version=2023-11-01" \
  -o none 2>/dev/null; then
  skip "$BUDGET"
else
  if [ -z "${BUDGET_EMAIL:-}" ]; then read -rp "   Email for the budget alert (blank to skip): " BUDGET_EMAIL; fi
  if [ -n "$BUDGET_EMAIL" ]; then
    AMOUNT="${BUDGET_AMOUNT:-5}"
    # The amount is in the subscription's billing currency. On an INR-billed
    # account 5 means five rupees; use BUDGET_AMOUNT=450 for roughly $5.
    START=$(date -u +%Y-%m-01T00:00:00Z)
    END="$(( $(date -u +%Y) + 1 ))-$(date -u +%m)-01T00:00:00Z"
    az rest --method put \
      --url "https://management.azure.com/subscriptions/$SUB/providers/Microsoft.Consumption/budgets/$BUDGET?api-version=2023-11-01" \
      --body "{
        \"properties\": {
          \"category\": \"Cost\",
          \"amount\": $AMOUNT,
          \"timeGrain\": \"Monthly\",
          \"timePeriod\": {\"startDate\": \"$START\", \"endDate\": \"$END\"},
          \"notifications\": {
            \"actual80\": {\"enabled\": true, \"operator\": \"GreaterThan\", \"threshold\": 80,
                           \"thresholdType\": \"Actual\", \"contactEmails\": [\"$BUDGET_EMAIL\"]},
            \"forecast100\": {\"enabled\": true, \"operator\": \"GreaterThan\", \"threshold\": 100,
                              \"thresholdType\": \"Forecasted\", \"contactEmails\": [\"$BUDGET_EMAIL\"]}
          }
        }
      }" -o none
    echo "   budget of $AMOUNT/month set, mailing $BUDGET_EMAIL at 80% actual and 100% forecast"
  else
    echo "   skipped"
  fi
fi

# ---------------------------------------------------------------- check

step "Health"
image=$(az containerapp show -n "$APP" -g "$RG" --query 'properties.template.containers[0].image' -o tsv)
if [ "$image" = "$PLACEHOLDER" ]; then
  echo "   still on the placeholder image; the real one arrives with the first"
  echo "   Deploy API run, which pushing main starts (backend/ has changed)."
else
  echo "   $API_BASE/health (a cold replica takes up to a minute)"
  for attempt in $(seq 1 12); do
    if body=$(curl -fsS --max-time 20 "$API_BASE/health" 2>/dev/null); then
      echo "   $body"
      break
    fi
    sleep 10
  done
fi

cat <<EOF

Done. Before pushing main, make sure VITE_API_BASE is set on the repository
(step 7 above): the site build bakes it in, and without it every visitor gets
the recorded run. Then:

  git push origin main       # also runs Deploy API: builds the image, rolls it out
  gh run watch --repo $REPO  # pick the Deploy API run

and when it has finished, open https://kirtikar.me cold: the chip should read
"Server live".
EOF
