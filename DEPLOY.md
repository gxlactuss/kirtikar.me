# Running the demo live

The site at kirtikar.me and the API it calls are deployed separately:

| Piece | Where | Deployed by |
| --- | --- | --- |
| The site | GitHub Pages | `.github/workflows/deploy.yml` on push to `main` |
| The API | Azure Container Apps | `.github/workflows/deploy-api.yml` when `backend/**` changes |
| Noticing the API has died | GitHub Actions cron | `.github/workflows/keepalive.yml`, once a day |

`backend/` is a deployment copy of the service from the
`SIH-090-Project-Ctrl-Alt-Delete` repository, with the demo-mode changes
described below on top. It is not a fork to develop in: pipeline work belongs
in the original repository and should be copied across.

Everything below lives in one Azure subscription, in one region:

| | |
| --- | --- |
| Subscription | `f3849fe0-171c-4378-81ce-3c1769804ed0` |
| Region | `centralindia` |
| Resource group | `kirtikar-rg` |

Central India is not decoration. The demo's users and its judges are in India,
and so is Sarvam's speech API — the pipeline makes several round trips per run,
and putting the container anywhere else adds that latency to all of them.

> **Why not a Hugging Face Space?** That was the original target, and
> `backend/Dockerfile` still carries its fingerprints (port 7860, uid 1000).
> In July 2026 Hugging Face put the Docker SDK behind billing — free accounts
> get static Spaces only, and the CLI does not route around it. Container Apps
> runs the same image unmodified and stays inside its monthly free grant at
> this traffic, at the cost of the warm-start behaviour described below.

---

## Why the API needs DEMO_MODE

Every route on this service depends on `get_current_seller`, and the website
sends no `Authorization` header — there is nobody to log in as. Without
`DEMO_MODE` every call returns 401 and the site silently falls back to a
recorded run, which looks exactly like success and is the failure that is
hardest to notice.

`DEMO_MODE=true` resolves a request carrying *no* header to one shared seller
(`app/core/demo.py`). A header that is present but invalid is still a 401 —
falling back there would turn an expired token into a silent identity swap.

It is also what makes the photos load. A listing's `image_urls` point at an
authenticated route and the review screen renders them with a plain
`<img src>`, which cannot carry a bearer token.

**Never set `DEMO_MODE=true` on a deployment holding real artisans' listings.**
It makes every listing readable and editable by anyone who can reach it.

---

## First-time setup

**The short way:** `./tools/azure-setup.sh` after `az login`. It runs steps 1-7
below plus the budget alert, skips anything that already exists (so a pass that
stops halfway is finished by running it again), reads the two API keys from a
hidden prompt, and, when this GitHub account cannot set repository variables
(that needs admin, not push), prints the five values for someone who can. The
steps are spelled out below so each one can be understood and run by hand.

All of it is CLI. Sign in once and pin the subscription, so nothing below
silently lands in a different one:

```sh
az login
az account set --subscription f3849fe0-171c-4378-81ce-3c1769804ed0
az account show --query '{name:name, state:state}' -o table   # state: Enabled
```

Container Apps needs a subscription in good standing even though this
deployment is expected to cost nothing — the free grant applies to pay-as-you-go
subscriptions too. An expired free trial cannot run it; it has to be upgraded
or replaced.

### 1. Register the resource providers

A fresh subscription has none of these on, and the failure arrives much later
as an unhelpful "resource type not found".

```sh
for ns in Microsoft.App Microsoft.ContainerRegistry Microsoft.OperationalInsights; do
  az provider register --namespace "$ns" --wait
done
```

### 2. Create the resource group and the registry

The registry name is globally unique across Azure, so pick one and keep it —
it becomes the `AZURE_REGISTRY` repository variable in step 6.

```sh
RG=kirtikar-rg
LOC=centralindia
ACR=kirtikaracr           # must be globally unique, lowercase, no dashes

az group create --name "$RG" --location "$LOC"

az acr create \
  --resource-group "$RG" --name "$ACR" \
  --sku Basic --location "$LOC" \
  --admin-enabled true
```

`--admin-enabled true` is what lets the container app pull the image with a
username and password in step 5. A managed identity with `AcrPull` is the
better credential and the one to move to if this outlives the demo; it is not
used here because it has to be granted *after* the app exists, which turns a
one-command setup into a three-command one with a window in between where the
app cannot start.

Basic tier is ~$0.17/day. It is the one part of this deployment that is not
free, and the cheapest way to have a registry in the same region as the app.

### 3. Create the Container Apps environment

```sh
az containerapp env create \
  --name kirtikar-env \
  --resource-group "$RG" \
  --location "$LOC"
```

The environment is the network and logging boundary the app runs in. Creating
it also creates a Log Analytics workspace, which is where `az containerapp
logs` reads from — the only way to see a traceback from a failed run.

### 4. Get the registry credentials

```sh
ACR_USER=$(az acr credential show -n "$ACR" --query username -o tsv)
ACR_PASS=$(az acr credential show -n "$ACR" --query 'passwords[0].value' -o tsv)
```

### 5. Create the container app

This is the only step that carries the API keys, and it is deliberately not in
the workflow: an app cannot be created without them, and a workflow that had
them would have them in this repository's history.

Build the first image by hand, then create the app around it. Take
`SARVAM_API_KEY` and `GEMINI_API_KEY` from the source repository's
`backend/.env`:

```sh
az acr build --registry "$ACR" --image kirtikar-api:bootstrap \
  --file Dockerfile backend

az containerapp create \
  --name kirtikar-api \
  --resource-group "$RG" \
  --environment kirtikar-env \
  --image "$ACR.azurecr.io/kirtikar-api:bootstrap" \
  --registry-server "$ACR.azurecr.io" \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --target-port 7860 \
  --ingress external \
  --cpu 1 --memory 2Gi \
  --min-replicas 0 --max-replicas 1 \
  --secrets "sarvam-api-key=$SARVAM_API_KEY" "gemini-api-key=$GEMINI_API_KEY" \
  --env-vars \
    'CORS_ORIGINS=https://kirtikar.me,https://www.kirtikar.me,http://localhost:5173' \
    'SARVAM_API_KEY=secretref:sarvam-api-key' \
    'GEMINI_API_KEY=secretref:gemini-api-key'
```

The first build takes about ten minutes — most of it is installing onnxruntime
and baking in the 179MB IS-Net model.

Rotating a key afterwards never touches this repository:

```sh
az containerapp secret set -n kirtikar-api -g "$RG" \
  --secrets "gemini-api-key=$NEW_KEY"
az containerapp revision restart -n kirtikar-api -g "$RG" \
  --revision "$(az containerapp revision list -n kirtikar-api -g "$RG" \
                 --query '[?properties.active].name | [0]' -o tsv)"
```

Print the URL — this is what `VITE_API_BASE` becomes:

```sh
az containerapp show -n kirtikar-api -g "$RG" \
  --query 'properties.configuration.ingress.fqdn' -o tsv
# kirtikar-api.<something>.centralindia.azurecontainerapps.io
```

### 6. Let GitHub Actions deploy, without a stored credential

The workflow signs in with OIDC: GitHub mints a short-lived token that says
"this is a workflow on `main` of this repository", and Azure trades it for an
access token against a federated credential. **There is no client secret, and
nothing in repository secrets at all** — which is the failure mode a stored
deployer key always has and never announces.

```sh
SUB=f3849fe0-171c-4378-81ce-3c1769804ed0
REPO=krs-kaustubh/kirtikar.me      # owner/repo of THIS repository

APP_ID=$(az ad app create --display-name kirtikar-deployer --query appId -o tsv)
az ad sp create --id "$APP_ID"

az ad app federated-credential create --id "$APP_ID" --parameters "{
  \"name\": \"github-main\",
  \"issuer\": \"https://token.actions.githubusercontent.com\",
  \"subject\": \"repo:$REPO:ref:refs/heads/main\",
  \"audiences\": [\"api://AzureADTokenExchange\"]
}"
```

The subject is matched exactly, so this credential authorises pushes to `main`
and nothing else. A `workflow_dispatch` run from `main` matches it too; a run
from any other branch does not, and fails at the login step.

Grant it the two things a deploy needs — update the app, and push to the
registry — scoped to the resource group rather than the subscription:

```sh
az role assignment create --assignee "$APP_ID" --role Contributor \
  --scope "/subscriptions/$SUB/resourceGroups/$RG"
az role assignment create --assignee "$APP_ID" --role AcrPush \
  --scope "/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.ContainerRegistry/registries/$ACR"
```

Then print what goes into GitHub:

```sh
echo "AZURE_CLIENT_ID       $APP_ID"
echo "AZURE_TENANT_ID       $(az account show --query tenantId -o tsv)"
echo "AZURE_SUBSCRIPTION_ID $SUB"
echo "AZURE_REGISTRY        $ACR"
```

### 7. Set the repository's variables

In this repository, **Settings → Secrets and variables → Actions**. All five
are **variables**; the Secrets tab stays empty.

| Name | Value |
| --- | --- |
| `AZURE_CLIENT_ID` | the app id from step 6 |
| `AZURE_TENANT_ID` | the tenant id from step 6 |
| `AZURE_SUBSCRIPTION_ID` | `f3849fe0-171c-4378-81ce-3c1769804ed0` |
| `AZURE_REGISTRY` | `kirtikaracr` (or whatever you named it) |
| `VITE_API_BASE` | the app URL from step 5, `https://…`, no trailing slash |

None of these is sensitive: three are identifiers that are useless without the
federated trust, and `VITE_API_BASE` is a public URL that Vite inlines into the
bundle anyway. Making them secrets would only mask them in the logs and make a
failed deploy harder to read.

**`VITE_API_BASE` must be set before the site is built.** `src/api/client.ts`
falls back to `http://localhost:8000` when it is empty, which produces a
deployed bundle that calls localhost, fails every request, and shows a
recorded run to every visitor — the silent failure this file keeps warning
about. So the order is: create the app, read its URL, set the variable, *then*
push.

### 8. Check it

```sh
curl https://kirtikar-api.<something>.centralindia.azurecontainerapps.io/health
# {"status":"ok","service":"Listing Factory API","version":"0.1.0"}
```

Then open kirtikar.me. The chip in the top bar should read **Server live** with
a latency figure. If it reads **Demo data**, the run fell back to a recording
and the chip carries the reason.

From here on, pushing anything under `backend/` redeploys: **Deploy API** in
the Actions tab builds in ACR and rolls a new revision, and prints the URL.

---

## The service configuration is load-bearing

Four settings are not tuning, and changing any of them breaks something
specific:

- **`--max-replicas 1`.** The demo's rate limit counts in process memory
  (`app/core/demo_limit.py`), the database is a single SQLite file, and
  `BackgroundTasks` run in the serving process. All three assume one process,
  and a second replica would quietly break all three at once. It is the same
  reason the Dockerfile runs uvicorn with `--workers 1`.
- **`--target-port 7860`.** Ingress has no default that would work here; the
  Dockerfile listens on 7860, inherited from the Space it was written for.
- **`--cpu 1 --memory 2Gi`.** IS-Net wants about 1GB. Container Apps only
  accepts certain CPU/memory pairs, and 1 vCPU must be paired with 2Gi — this
  is not a number to round down.
- **`--min-replicas 0`.** What makes the deployment free, and what makes the
  first visit slow. See below.

One thing that has no equivalent here and needed one on Cloud Run: there is no
`--no-cpu-throttling` to set. Container Apps does not scope CPU to the lifetime
of a request, so the pipeline running in a `BackgroundTask` after the response
is sent (`app/api/routes/media.py`) gets a full core the same as anything else.
What can still cut it short is scaling to zero — see the next section.

---

## How "always on" actually works

It doesn't, quite, and that is a deliberate trade.

With `--min-replicas 0` the replica is scaled away a few minutes after the last
request, so most judges will arrive at a cold container and wait 40-60 seconds
for the image to pull and the app to import. Nothing pins a replica up, because
doing so — `--min-replicas 1` — means a 1 vCPU / 2GiB replica billed around the
clock: roughly 2.6M vCPU-seconds a month against a free grant of 180K
vCPU-seconds and 360K GiB-seconds, or about $30-40 a month against a deployment
that is otherwise free.

Three things carry that weight instead:

- **The scroll intro.** `src/intro/` mounts `<Stage>` from the first frame, so
  `BackendChip`'s health watcher starts waking the replica while the visitor
  is still scrolling. Twenty seconds of intro is twenty seconds off the wait.
- **The fallback.** `src/machine/run.ts` tries the network first and replays a
  recorded run on any failure, pacing it by that run's own measured timings. A
  cold start, an expired key or an exhausted quota all still produce a
  complete, honest run — labelled **Demo data** with the reason — rather than
  an error.
- **Within a session it stays warm.** Once the first request lands, the replica
  serves the whole run, and the site's polling is itself the traffic that keeps
  the HTTP scale rule from scaling it away mid-pipeline. Only the first hit
  pays.

That last point is the one to remember if the frontend ever stops polling
during a run: a background task with no in-flight requests is exactly what
scale-to-zero is built to reclaim, and the pipeline would be killed partway
with nothing in the logs to say why.

The daily cron is not a keep-alive and cannot be mistaken for one. Its job is
that **a failed scheduled run emails the repository owner**, which for an
unattended month is the only way anyone learns the API has stopped answering
before a judge does.

Note also: **GitHub disables scheduled workflows in a repository with 60 days
of no activity.** That does not bite inside a one-month window that starts now.

---

## What is ephemeral

A replica shutdown takes the SQLite database and every uploaded photo with it —
the container filesystem is scratch space on the node, not a volume. Because
replicas are reclaimed within minutes of going idle, this happens many times a
day rather than rarely.

The site already handles it: a 404 on a listing it was polling is read as "the
server restarted" and falls back to a recorded run.

It does mean **nothing a judge creates survives their visit.** Nothing in the
demo depends on it doing so.

---

## When something is wrong

The revision, and whether it is actually running:

```sh
az containerapp revision list -n kirtikar-api -g kirtikar-rg \
  --query '[].{name:name, active:properties.active, replicas:properties.replicas, state:properties.runningState}' -o table
```

The application's own output, which is where a traceback from a failed run
turns up (there is a ~2 minute lag before new lines are queryable):

```sh
az containerapp logs show -n kirtikar-api -g kirtikar-rg --type console --tail 100
```

Why a replica will not start at all — an image it cannot pull, a bad secret
reference:

```sh
az containerapp logs show -n kirtikar-api -g kirtikar-rg --type system --tail 50
```

---

## Things that would bite later

- **Dependencies are pinned, and the pins are the tested set.**
  `backend/requirements.txt` pins the direct dependencies and
  `backend/constraints.txt` every transitive one, both resolved for the
  image's platform (linux/x86-64, Python 3.11) on 2026-09-23; the backend
  suite passes against them. A mid-window redeploy builds exactly this set. To
  upgrade anything, loosen it, rebuild, run the tests, and regenerate both
  files together.
- **The free grant is a budget, not a guarantee.** 180K vCPU-seconds and 360K
  GiB-seconds a month is generous against bursty judging traffic, but a runaway
  loop or a stuck replica would eat it. Set a budget alert at $5 on the
  subscription (Cost Management → Budgets); it is the cheapest possible smoke
  detector, and it will also catch the registry's ~$5/month if nothing else
  does.
- **The registry admin password is a long-lived credential**, stored on the
  container app as a secret. It is the one piece of this setup that a stolen
  subscription-reader role could use. Moving the app to a system-assigned
  managed identity with `AcrPull` removes it, and is the right thing to do if
  this outlives the demo.
- **The federated credential is pinned to `refs/heads/main`.** A deploy from a
  branch, a tag, or a fork's pull request fails at the login step rather than
  running with the wrong permissions. That is the intended behaviour; if you
  need a staging branch to deploy, add a second federated credential rather
  than loosening the subject.
- **Six of the ten bundled craft photos fail the image subject gate** —
  pottery, handloom, embroidery, Madhubani, leather and bamboo are
  photographed in context rather than against a plain background, so a run on
  them ends in `needs_attention` asking for a retake. That is the pipeline
  working correctly. Jewellery, metalwork, wood carving and the sindoor boxes
  pass, so `src/app/crafts.ts` puts them first in the rail: a judge's first
  try should end in a finished listing. Re-measure before reordering.
- **A voice note is transcribed live or not at all.** Sarvam's `saaras:v3`
  is served only from `/speech-to-text` with `mode=translate`; the service
  used to call the legacy `/speech-to-text-translate`, which rejects v3, and
  hid every failure behind a canned transcript about a Madhubani painting. If
  a run ends asking the visitor to record again, read the console log for the
  Sarvam status code before suspecting anything else.
