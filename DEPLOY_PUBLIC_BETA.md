# Deploy OmicsRoute with Vercel Services

The `vercel-no-precomputed` branch combines the original benchmark baseline
(`6cb1bef`) with the Vercel Services deployment configuration. The API and
catalogue engine match the baseline: coverage is calculated on every request.
No coverage generation step, generated snapshot, startup coverage calculation,
or catalogue caching is required.

## Project settings

Import `g0g0sama/omicsroute-debug` into Vercel, or select this branch for an
existing project's deployment:

- Branch: `vercel-no-precomputed`.
- Root Directory: repository root, rather than `frontend/`.
- Framework Preset: **Services**.
- Node.js: **22.x**. Python is pinned to **3.12** in `.python-version`.
- Use the default service build commands; remove any dashboard build override
  that invokes `scripts.precompute_coverage`.
- Leave `NEXT_PUBLIC_OMICSROUTE_API_URL` unset in every environment used for
  this branch. Remove any existing localhost or Render override before building.

The checked-in `vercel.json` defines the Next.js frontend and the FastAPI backend
with entrypoint `api.main:app`. `/health` and `/v1/*` route to the backend; all
remaining paths route to the frontend. The browser calls the API on the same
origin, so separate backend hosting and production CORS configuration are
unnecessary for this setup.

Vercel Services configuration reference:
<https://vercel.com/kb/guide/vercel-services>.

## Local development

From the repository root, use Python 3.12:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

In `frontend/.env.local`, set:

```text
NEXT_PUBLIC_OMICSROUTE_API_URL=http://127.0.0.1:8000
```

Then run the frontend in a second terminal with Node 22:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. Remove the local API URL override before a Vercel
build. Next.js embeds this public environment variable at build time.

## Verification

Run the existing validators from the repository root:

```bash
.venv/bin/python tests/api_foundation_v1/validate_api_foundation_v1.py
.venv/bin/python tests/web_parity_v1/validate_web_parity_v1.py
.venv/bin/python tests/metagenome_platform_coverage_v1/validate_metagenome_platform_coverage_v1.py
```

Build the frontend with the API URL unset:

```bash
cd frontend
npm ci
npm run build
```

For a deployment, verify `/health`, `/v1/sample-types`, and
`/v1/catalog/coverage`, then build short-read and long-read workflows and check
both Markdown and JSON downloads. The coverage endpoint does the original
calculation per request, so allow it to finish when checking API connectivity.

Completed benchmark records remain on the existing branches. This branch adds
no new performance measurements and requires no precomputation artifact.
