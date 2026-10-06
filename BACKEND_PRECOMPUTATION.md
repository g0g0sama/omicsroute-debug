# Coverage performance and free Render deployment

Normal coverage requests now return a snapshot generated during the Render
build and loaded once at FastAPI startup. Catalogue changes take effect after
rebuilding and restarting the API. Dependency audits remain explicit, dynamic
requests; they do not modify the snapshot.

This removes catalogue calculation from normal requests. It does not prevent
a free Render service from sleeping after 15 minutes without inbound traffic.
Render documents a wake-up time of about one minute:
<https://render.com/docs/free>.

## Build and run locally

Use Python 3.11. From the repository root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m scripts.precompute_coverage
.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

The generator writes `build/coverage.json` (ignored by Git). It can also take
`--output PATH` for inspection or tests. Render regenerates the default file
on every build. A process without an artifact calculates coverage once at
startup for local development. An unreadable or invalid artifact fails startup
with a regeneration instruction. Build failure must not be bypassed.

Parsed catalogue YAML and its workflow context index are cached by absolute
path, modification time and size. Live calculations therefore refresh when
files change. Returned contexts are copied so annotations cannot contaminate
the cached index. Audits calculate current coverage independently of the
startup snapshot.

## Deploy the baseline first

The original baseline is `6cb1beff66f2338712ab1bfeb798fe3a0f8c5ae2` in
`g0g0sama/omicsroute-debug`. Keep the remote `debug` branch at that commit until
the deployed baseline measurements have been captured.

Create a Render **Web Service** named `omicsroute-debug-api`, with the repository
root, branch `debug`, Python runtime and **Free** instance type. Baseline settings:

```text
Build Command: pip install -r requirements.txt
Start Command: python -m uvicorn api.main:app --host 0.0.0.0 --port $PORT
Health Check Path: /health
OMICSROUTE_CORS_ORIGINS=https://omicsroute-debug.vercel.app
```

Use Python 3.11 for both versions. For the baseline, set `PYTHON_VERSION` to a
fully qualified released 3.11 version in the dashboard, then use that same
value for the optimized deployment. The optimized checkout also includes a
`.python-version` file selecting 3.11. Render's version precedence is documented
at <https://render.com/docs/python-version>.

Configure Vercel project `omicsroute-debug` with repository branch `debug`,
root directory `frontend`, Node 22, install command `npm ci` and build command
`npm run build`. Set this variable in the Production environment:

```text
NEXT_PUBLIC_OMICSROUTE_API_URL=https://omicsroute-debug.onrender.com
```

Redeploy Vercel after setting it: this browser URL is embedded at build time.
Use the actual Render URL, not a guessed service hostname. Environment changes
apply to subsequent deployments:
<https://vercel.com/docs/environment-variables>.

The Vercel frontend was observed live at `https://omicsroute-debug.vercel.app`
on 2026-10-06, but its baseline bundle still used `http://127.0.0.1:8000`.
The user supplied `https://omicsroute-debug.onrender.com` as the backend URL.
An initial `/health` request timed out after 120 seconds; the service and completed
platform configuration are not yet verified.

## Measure and deploy the optimized version

Use the benchmark utility from the optimized checkout even when the deployed
service is running the baseline. It does not require an application change on
the server. It records raw sequential request timings, canonical response hashes,
successful/failed counts, median and nearest-rank p95.

```bash
.venv/bin/python -m scripts.benchmark_api \
  --base-url https://omicsroute-debug.onrender.com \
  --label baseline-render \
  --commit 6cb1beff66f2338712ab1bfeb798fe3a0f8c5ae2 \
  --samples 20 --idle-seconds 960 \
  --output build/benchmarks/baseline-render.json
```

During the idle interval, close browser tabs and stop external monitors and
manual requests. The utility itself sends no application requests for 16
minutes. Afterward it records `/health` readiness within a 120-second budget,
then the first coverage request, followed by a warmup and 20 sequential requests
for each endpoint. If Render sends a non-JSON loading response, all readiness
attempts are retained instead of counting it as a successful API response.

The idle interval alone does not establish that spin-down occurred. The output
sets `spin_down_confirmed` to false; attach Render log evidence separately when
available. Do not interpret warm endpoint improvements as a wake-up improvement.

After baseline measurements, publish the optimized commit to `debug`. For a
dashboard-created Render service, update its build command explicitly:

```text
pip install -r requirements.txt && python -m scripts.precompute_coverage
```

The checked-in `render.yaml` contains that command, branch `debug`, the free
plan and the health check. Dashboard-created services do not automatically
adopt Blueprint changes. Trigger the new deploy and verify the deployed commit
in Render and Vercel before testing. Repeat the command above with label
`optimized-render`, the actual optimized commit hash and a separate output file.

## Checks and browser demonstration

Install `httpx` in the development environment for API tests:

```bash
.venv/bin/python -m pip install httpx
.venv/bin/python -m unittest discover -s tests/coverage_precomputation -v
.venv/bin/python tests/api_foundation_v1/validate_api_foundation_v1.py
.venv/bin/python tests/web_parity_v1/validate_web_parity_v1.py
.venv/bin/python tests/metagenome_platform_coverage_v1/validate_metagenome_platform_coverage_v1.py
```

Browser checks additionally require Playwright and its Chromium browser:

```bash
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python -m scripts.smoke_frontend \
  --base-url https://omicsroute-debug.vercel.app \
  --output build/browser-smoke-render
```

The browser check builds Metagenome Illumina paired-end functional profiling
and Oxford Nanopore long-read taxonomic profiling workflows. It verifies both
downloads match the API exports, checks JSON parsing, records page errors, and
saves desktop/mobile screenshots. Run it after the idle measurements so it
does not keep the backend awake during them.

The frontend source, dependency manifests, scientific catalogue definitions and
API response formats are unchanged. The local measurements and verification
status are recorded under `audit/backend_precomputation_v1/`.

## Rollback and scientist handover

Keep the baseline and optimized commit hashes and the Render build command with
the results. Use the provider's previous-deployment rollback controls when
available; otherwise deploy the baseline commit and restore the baseline build
command. The baseline has no `scripts.precompute_coverage` module, so the new
build command cannot be used to rebuild it.

When the scientist adopts the patch, retain her existing service names, branches
and domains. Transfer the backend changes, generator and build command; configure
her actual Vercel origin in CORS and her actual Render URL in Vercel. No database,
Redis, persistent disk, keep-alive traffic or paid instance is added by this patch.
