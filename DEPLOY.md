# Running the demo live

The site at kirtikar.me and the API it calls are deployed separately:

| Piece | Where | Deployed by |
| --- | --- | --- |
| The site | GitHub Pages | `.github/workflows/deploy.yml` on push to `main` |
| The API | A Hugging Face Docker Space | `.github/workflows/deploy-api.yml` when `backend/**` changes |
| Keeping the API awake | GitHub Actions cron | `.github/workflows/keepalive.yml`, every 15 minutes |

`backend/` is a deployment copy of the service from the
`SIH-090-Project-Ctrl-Alt-Delete` repository, with the demo-mode changes
described below on top. It is not a fork to develop in: pipeline work belongs
in the original repository and should be copied across.

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

### 1. Create the Space

New Space → **Docker** → blank template. CPU basic (free) is enough: it has
16GB of RAM, and the pipeline's ceiling is the ~1GB the IS-Net model wants.

### 2. Set the Space's secrets

In the Space, **Settings → Variables and secrets**:

| Name | Kind | Value |
| --- | --- | --- |
| `SARVAM_API_KEY` | secret | from the source repo's `.env` |
| `GEMINI_API_KEY` | secret | from the source repo's `.env` |
| `CORS_ORIGINS` | variable | `https://kirtikar.me,https://www.kirtikar.me,http://localhost:5173` |

The keys are deliberately *not* injected by the deploy workflow: anything it
pushed would sit in the Space's git history and would need a re-push to
rotate.

`DEMO_MODE`, `DATABASE_URL`, `MEDIA_STORAGE_DIR` and
`PIPELINE_MAX_STAGE_ATTEMPTS` are already set in the `Dockerfile` and need no
configuration.

### 3. Set the repository's variables and secret

In this repository, **Settings → Secrets and variables → Actions**:

| Name | Kind | Value |
| --- | --- | --- |
| `VITE_API_BASE` | variable | `https://<user>-kirtikar-api.hf.space` — no trailing slash, no `/api/v1` |
| `HF_SPACE_ID` | variable | `<user>/kirtikar-api` |
| `HF_TOKEN` | secret | a **write** token from huggingface.co/settings/tokens |

`VITE_API_BASE` is a variable rather than a secret on purpose: Vite inlines it
into the bundle, so it is public either way, and masking it would only make a
failed deploy harder to read.

### 4. Deploy

Push to `main`, or run **Deploy API** and then **Deploy** from the Actions tab.
The first Space build takes about ten minutes — most of it is installing
onnxruntime and baking in the 179MB IS-Net model.

### 5. Check it

```sh
curl https://<user>-kirtikar-api.hf.space/health
# {"status":"ok","service":"Listing Factory API","version":"0.1.0"}
```

Then open kirtikar.me. The chip in the top bar should read **Server live** with
a latency figure. If it reads **Demo data**, the run fell back to a recording
and the chip carries the reason.

---

## How "always on" actually works

A free Space sleeps after **48 hours** without traffic and then needs 60-180
seconds to wake. Judging runs unannounced across a month, so the keep-alive
workflow pings `/health` every 15 minutes. That keeps the Space from ever
reaching the idle threshold and keeps the process hot, so the IS-Net model
stays loaded and the first real visitor does not pay for the warm-up.

Two things to know about that safety net:

- **GitHub disables scheduled workflows in a repository with 60 days of no
  activity.** That does not bite inside a one-month window that starts now, but
  it is why the cron is not the only defence.
- **A failed ping emails the repository owner.** For an unattended month that
  is the only way anyone learns the API has stopped answering before a judge
  does.

The site is not betting everything on this. `src/machine/run.ts` tries the
network first and replays a recorded run on any failure, pacing it by that
run's own measured timings. A sleeping Space, an expired key or an exhausted
quota all still produce a complete, honest run — labelled **Demo data** with
the reason — rather than an error.

---

## What is ephemeral

A Space restart (a rebuild, a config change, or the platform moving it) takes
the SQLite database and every uploaded photo with it. That is fine, and the
site already handles it: a 404 on a listing it was polling is read as "the
Space restarted" and falls back to a recorded run.

It does mean **nothing a judge creates survives a restart.** Nothing in the
demo depends on it doing so.

---

## Things that would bite later

- **`backend/requirements.txt` pins nothing** — every dependency is `>=`. The
  Space only rebuilds when something is pushed to it, so a running deployment
  is stable; but a redeploy during the judging window could pull a new rembg or
  onnxruntime and build something that was never tested. If you have to
  redeploy mid-window, check the Space's build log before trusting it.
- **The demo's rate limit is per process and in memory**
  (`app/core/demo_limit.py`, 20 listings per address per hour). A restart hands
  everyone their allowance back. It protects the API budget, not much else.
- **The bundled craft photos fail the image subject gate** — they are
  photographed in context rather than against a plain background, so a run ends
  in `needs_attention` with a framing note. That is the pipeline working
  correctly and matches the recorded fixtures, which end the same way.
