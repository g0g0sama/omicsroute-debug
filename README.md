# OmicsRoute

**OmicsRoute** is an evidence-aware bioinformatics workflow planning and decision-support system. It helps users choose analysis strategies and candidate tools from the biological context, data state, sequencing technology, analysis goal, dataset constraints, technical dependencies, and available compute environment.

🌐 **Public beta:** https://omicsroute.vercel.app

> **Status:** `v0.1.0-beta.1` — public beta. OmicsRoute plans workflows; it does not execute the underlying bioinformatics tools.

## What OmicsRoute does

OmicsRoute builds context-specific workflow plans rather than returning a generic tool list. Its decision layers keep different questions separate:

- scientific fit;
- technical input/output and dependency compatibility;
- dataset-specific PASS / WARNING / BLOCK constraints;
- operational and compute feasibility;
- fallback and recovery strategies;
- literature and registry evidence.

A technically blocked tool is not silently replaced with an unrelated method.

## Current scope

The public beta includes workflow planning across:

- bacterial isolate genomics;
- eukaryotic genome analysis;
- environmental shotgun metagenomics;
- amplicon analysis;
- bulk transcriptomics;
- metatranscriptomics;
- virome and phage-oriented analysis.

Coverage includes Illumina contexts and supported long-read / hybrid contexts for Oxford Nanopore and PacBio where curated routes are available.

The planner can also start from downstream data states such as genome assemblies, viral FASTA files, ASV/OTU/feature tables, count matrices, ranked gene lists, and other supported artifacts.

## Web application

The public application uses:

```text
Next.js frontend
      ↓
FastAPI backend
      ↓
OmicsRoute Python decision engine
      ↓
Curated YAML catalogues + optional external evidence services
```

The web planner does **not** upload FASTQ, FASTA, BAM, count-table, or other sequencing files. Users describe their analysis context and OmicsRoute returns a workflow plan.

## Recommendation logic

OmicsRoute evaluates recommendations through separate layers:

1. **Scientific fit** — whether a method is appropriate for the requested biological analysis.
2. **Dependency validation** — whether required input artifacts can be produced by upstream steps.
3. **Dataset constraints** — explicit applicability rules encoded as PASS / WARNING / BLOCK / needs-input states.
4. **Operational feasibility** — compute and runtime suitability based on the user-entered environment.
5. **Fallback semantics** — direct alternatives, alternate workflow strategies, or remediation guidance.
6. **Evidence support** — literature and registry information used as supporting context rather than as a substitute for hard technical rules.

Recommendation scores are OmicsRoute support scores within the curated catalogue; they are not universal measures of tool quality.

## Reference support

For supported genome contexts, OmicsRoute includes a reference-finder workflow that can query NCBI taxonomy and genome-assembly information. Reference availability and reference suitability are treated separately from merely finding an assembly.

## Export

Generated workflow plans can be exported as:

- Markdown;
- JSON.

Exports are intended for analysis planning, methods drafting, sharing, and reproducibility notes.

## Validation

The repository contains internal scientific and software validation suites covering:

- recommendation scenarios;
- workflow dependency structure;
- constraint-aware ranking;
- fallback semantics;
- context and platform coverage;
- UI/export integration;
- catalogue consistency;
- web end-to-end integration.

Before the `v0.1.0-beta.1` public-beta milestone, the catalogue/backend coverage audit and the web end-to-end smoke test completed with zero critical/high issues.

These are **internal regression and consistency checks**, not an independent scientific gold-standard benchmark.

## Run locally

### Backend

From the repository root:

```powershell
& ".\.venv\Scripts\python.exe" -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

The API is then available at:

```text
http://127.0.0.1:8000
```

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

### Frontend

In a second terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Then open:

```text
http://localhost:3000
```

For local development, the frontend defaults to `http://127.0.0.1:8000` unless `NEXT_PUBLIC_OMICSROUTE_API_URL` is set.

## Repository structure

```text
api/                   FastAPI web API
frontend/              Next.js public web interface
engine/                Recommendation, validation, scoring, and routing logic
data/                  Workflow, tool, artifact, constraint, and capability catalogues
services/              NCBI, literature, and registry integrations
tests/                 Scientific and software validation suites
app.py                  Legacy/alternative Streamlit interface
```

## Deployment

The current public beta is deployed as:

- **Frontend:** Vercel
- **Backend:** Render

See `DEPLOY_PUBLIC_BETA.md` for deployment details.

The free backend may require a short cold-start period after inactivity. This is an infrastructure limitation rather than a workflow-engine requirement.

## Feedback

Beta feedback can be submitted from the **Send feedback** control in the web interface or through the repository's GitHub issue template.

Please do not submit confidential, patient-identifiable, or otherwise sensitive information in public issues.

## Project status

OmicsRoute is under active development. The current public deployment is intended for research-software beta testing while catalogue expansion, external evaluation, documentation, and manuscript preparation continue.

## Disclaimer

OmicsRoute provides bioinformatics workflow decision support. Recommendations should be interpreted together with the user's dataset, experimental design, computational environment, reference databases, and the current documentation of the underlying bioinformatics tools.
