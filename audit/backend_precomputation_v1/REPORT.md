# Backend precomputation verification

## Local HTTP comparison

Baseline: `6cb1beff66f2338712ab1bfeb798fe3a0f8c5ae2`.
Optimized application code: `e694b564329c1340828dbdca8193df22d2a8027b`.
Both used Python 3.11.2 and the same installed dependencies on this machine.
The baseline was run from a separate checkout with an unmodified API.

Each endpoint had one warmup followed by 20 sequential requests using a persistent
HTTP session. Each request succeeded. Timings include the HTTP response body.
p95 uses the nearest-rank method. Host load was not controlled; these are local
measurements, not a Render or internet-latency claim.

| Endpoint | Baseline median ms | Baseline p95 ms | Optimized median ms | Optimized p95 ms |
| --- | ---: | ---: | ---: | ---: |
| `/health` | 2.050 | 2.110 | 0.819 | 0.949 |
| `/v1/sample-types` | 1.796 | 2.139 | 0.555 | 0.862 |
| `/v1/catalog/coverage` | 8562.694 | 8661.649 | 2.158 | 3.066 |

Every canonical response hash matched between versions, across all samples and
all three endpoints. This includes the full coverage payload, rather than just
its aggregate counts. Coverage remains 57 supported goals out of 58 across seven
families, with one planned goal.

Raw results: [baseline](baseline-local.json), [optimized](optimized-local.json).

## Correctness checks

- Eight regression tests passed: artifact round trip, one YAML parse per source,
  one index per calculation, invalidation after file changes (including a same-size
  edit), context isolation, one-time missing-artifact fallback, invalid-artifact
  startup failure, startup warmup without per-request calculation, and audit
  isolation (some tests cover several related conditions).
- Existing API foundation, web parity and Metagenome platform validators passed.
- A real HTTP dependency audit validated 57 goals, with zero broken and one
  planned, and left the subsequent normal coverage response identical.
- The unchanged frontend built successfully under Node 22.13.1.
- Local Chromium built Illumina paired-end functional profiling and Oxford
  Nanopore long-read taxonomic profiling workflows. Both Markdown and JSON
  downloads exactly matched their API exports. No JavaScript page errors were
  recorded. Desktop and mobile screenshots were saved under
  `build/browser-smoke/`. [Browser results](browser-local.json).
- No frontend source, frontend dependency manifest, scientific catalogue or
  production Python requirement was changed.

## Deployment status

The baseline is published on remote branch `debug`. Vercel deployed that commit
at <https://omicsroute-debug.vercel.app>. Its initially observed bundle points to
localhost and requires its production API environment variable and a redeploy.
The user supplied backend URL <https://omicsroute-debug.onrender.com>.
The first `/health` request timed out after 120 seconds. A separate curl request
established TCP and TLS in under 100 ms but received no HTTP bytes within its
10-second limit. This does not establish whether the Render service is sleeping,
still deploying, or failing startup; dashboard status/logs are required.

Render baseline/optimized timings, confirmed idle behavior, deployed browser
checks, and optimized deployment commit IDs are pending. None of the local
results above establishes a deployed wake-up improvement. Free Render's
15-minute idle sleep remains part of the chosen architecture.

Follow [the deployment and handover guide](../../BACKEND_PRECOMPUTATION.md) for
configuration, 16-minute idle measurements, validation and rollback.
