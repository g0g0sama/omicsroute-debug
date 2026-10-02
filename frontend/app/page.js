"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  getBioTools,
  getCoverage,
  getDataStates,
  getGoals,
  getHealth,
  getReadTypes,
  getReferenceContext,
  getReferenceGuidance,
  getSampleTypes,
  getSequencingOptions,
  getStrategies,
  getToolEvidence,
  inspectWorkflow,
  researchAlternatives,
  researchWorkflow,
  searchAssemblies,
  searchTaxa,
} from "@/lib/api";

const RAW_READS = "raw_reads";

const FEEDBACK_URL =
  "https://github.com/isilayc/omicsroute/issues/new?template=beta-feedback.yml&title=%5BBeta%20feedback%5D%20";

const DEFAULT_COMPUTE = {
  enabled: false,
  operating_system: "Windows",
  ram_gb: 16,
  cpu_cores: 8,
  free_disk_gb: 100,
  dataset_scale: "Moderate",
  internet: "Normal",
  gpu_available: false,
  wsl_available: false,
  container_available: false,
  hpc_available: false,
  large_database_ok: false,
  web_services_allowed: true,
};

function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

function prettyId(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function downloadText(filename, content, mime) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function SelectField({
  label,
  value,
  onChange,
  options,
  disabled = false,
  help = "",
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
      >
        <option value="">Select...</option>
        {options.map((option) => {
          const item =
            typeof option === "string"
              ? { value: option, label: option }
              : option;

          return (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          );
        })}
      </select>
      {help ? <small>{help}</small> : null}
    </label>
  );
}

function StatusPill({ status, children }) {
  const label =
    children ||
    {
      ready: "Ready",
      needs_input: "Needs input",
      already_satisfied: "Already satisfied",
      unavailable: "Unavailable",
      pass: "PASS",
      warning: "WARNING",
      block: "BLOCK",
      not_defined: "Not defined",
      runnable: "Runnable",
      unknown: "I/O unknown",
      blocked: "Blocked",
      good: "Good",
      not_evaluated: "Not evaluated",
    }[status] ||
    status ||
    "Unknown";

  return (
    <span className={cx("status-pill", `status-${status || "neutral"}`)}>
      {label}
    </span>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ScoreBar({ label, value = 0, max = 1 }) {
  const numericValue = Number(value || 0);
  const numericMax = Number(max || 1);
  const width = Math.max(
    0,
    Math.min(100, (numericValue / numericMax) * 100)
  );

  return (
    <div className="score-row">
      <div className="score-row-head">
        <span>{label}</span>
        <strong>
          {numericValue}/{numericMax}
        </strong>
      </div>
      <div className="score-track">
        <div className="score-fill" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

function ReferenceFinder({
  sampleType,
  dataState,
  supported,
  referenceContext,
  setReferenceContext,
}) {
  const [mode, setMode] = useState("find");
  const [query, setQuery] = useState("");
  const [taxa, setTaxa] = useState([]);
  const [taxId, setTaxId] = useState("");
  const [assemblies, setAssemblies] = useState([]);
  const [accession, setAccession] = useState("");
  const [manualAccession, setManualAccession] = useState("");
  const [loading, setLoading] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setMode("find");
    setQuery("");
    setTaxa([]);
    setTaxId("");
    setAssemblies([]);
    setAccession("");
    setManualAccession("");
    setError("");

    if (supported) {
      setReferenceContext({
        status: "unresolved",
        usable_reference: false,
      });
    } else {
      setReferenceContext(null);
    }
  }, [sampleType, dataState, supported, setReferenceContext]);

  if (!supported) return null;

  async function handleTaxaSearch() {
    if (!query.trim()) return;
    setLoading("taxa");
    setError("");

    try {
      const result = await searchTaxa(query.trim());
      const rows = result.results || [];
      setTaxa(rows);
      setTaxId(rows[0]?.tax_id ? String(rows[0].tax_id) : "");
      setAssemblies([]);
      setAccession("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading("");
    }
  }

  async function handleAssemblySearch() {
    if (!taxId) return;
    setLoading("assemblies");
    setError("");

    try {
      const result = await searchAssemblies(taxId);
      const rows = result.assemblies || [];
      setAssemblies(rows);
      setAccession(rows[0]?.accession || "");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading("");
    }
  }

  async function useAssembly(selectedAccession) {
    if (!selectedAccession) return;
    setLoading("reference");
    setError("");

    try {
      const result = await getReferenceContext(selectedAccession);
      if (!result.ok || !result.reference_context) {
        throw new Error(
          result.error || "The assembly could not be resolved."
        );
      }
      setReferenceContext(result.reference_context);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading("");
    }
  }

  function changeMode(nextMode) {
    setMode(nextMode);
    setError("");

    if (nextMode === "none") {
      setReferenceContext({
        status: "no_reference",
        usable_reference: false,
      });
    } else if (nextMode === "skip") {
      setReferenceContext({
        status: "unresolved",
        usable_reference: false,
      });
    } else {
      setReferenceContext({
        status: "unresolved",
        usable_reference: false,
      });
    }
  }

  const selectedTaxon = taxa.find(
    (item) => String(item.tax_id) === String(taxId)
  );

  const speciesLike = [
    "species",
    "subspecies",
    "strain",
    "varietas",
    "forma",
  ].includes(String(selectedTaxon?.rank || "").toLowerCase());

  return (
    <div className="panel soft-panel">
      <div className="panel-head">
        <div>
          <span className="section-number">Reference</span>
          <h3>Organism & reference genome</h3>
        </div>
        {referenceContext?.usable_reference ? (
          <StatusPill status="pass">Reference selected</StatusPill>
        ) : (
          <StatusPill status="needs_input">Optional context</StatusPill>
        )}
      </div>

      <div className="segmented">
        {[
          ["find", "Find it for me (NCBI)"],
          ["manual", "I have an accession"],
          ["none", "No suitable reference / de novo"],
          ["skip", "Skip for now"],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={cx(mode === id && "active")}
            onClick={() => changeMode(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === "find" ? (
        <div className="stack">
          <div className="inline-form">
            <label className="field grow">
              <span>Organism</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Scientific/common name or Taxonomy ID"
              />
            </label>
            <button
              className="secondary-button align-end"
              type="button"
              onClick={handleTaxaSearch}
              disabled={!query.trim() || loading === "taxa"}
            >
              {loading === "taxa" ? "Searching..." : "Search NCBI"}
            </button>
          </div>

          {taxa.length ? (
            <div className="inline-form">
              <SelectField
                label="Matched organism"
                value={taxId}
                onChange={(value) => {
                  setTaxId(value);
                  setAssemblies([]);
                  setAccession("");
                }}
                options={taxa.map((item) => ({
                  value: String(item.tax_id),
                  label: `${item.scientific_name || item.tax_id}${
                    item.common_name ? ` (${item.common_name})` : ""
                  }${item.rank ? ` · ${item.rank}` : ""}`,
                }))}
              />
              <button
                className="secondary-button align-end"
                type="button"
                onClick={handleAssemblySearch}
                disabled={!taxId || loading === "assemblies" || !speciesLike}
              >
                {loading === "assemblies"
                  ? "Checking..."
                  : "Find genome assemblies"}
              </button>
            </div>
          ) : null}

          {selectedTaxon && !speciesLike ? (
            <div className="notice warning">
              This match is above species level. Choose a
              species/subspecies/strain before treating an assembly as a
              same-organism reference.
            </div>
          ) : null}

          {assemblies.length ? (
            <div className="inline-form">
              <SelectField
                label="Reference / assembly candidate"
                value={accession}
                onChange={setAccession}
                options={assemblies.map((item) => ({
                  value: item.accession,
                  label: `${item.accession} · ${
                    item.refseq_category ||
                    (item.is_reference
                      ? "Reference genome"
                      : item.is_representative
                      ? "Representative genome"
                      : item.source || "Assembly")
                  } · ${item.assembly_level || "level not reported"}`,
                }))}
              />
              <button
                className="primary-button align-end"
                type="button"
                onClick={() => useAssembly(accession)}
                disabled={!accession || loading === "reference"}
              >
                {loading === "reference"
                  ? "Selecting..."
                  : "Use this assembly"}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {mode === "manual" ? (
        <div className="inline-form">
          <label className="field grow">
            <span>NCBI Assembly accession</span>
            <input
              value={manualAccession}
              onChange={(event) =>
                setManualAccession(event.target.value.toUpperCase())
              }
              placeholder="GCF_... or GCA_..."
            />
          </label>
          <button
            className="primary-button align-end"
            type="button"
            onClick={() => useAssembly(manualAccession)}
            disabled={!manualAccession.trim() || loading === "reference"}
          >
            {loading === "reference" ? "Verifying..." : "Verify accession"}
          </button>
        </div>
      ) : null}

      {mode === "none" ? (
        <div className="notice info">
          Reference-based goals will stay hidden; de novo and
          assembly-oriented routes remain available.
        </div>
      ) : null}

      {mode === "skip" ? (
        <div className="notice info">
          Reference-dependent goals will stay hidden for now.
        </div>
      ) : null}

      {referenceContext?.usable_reference ? (
        <div className="selected-reference">
          <strong>
            {referenceContext.organism_name || "Organism resolved"}
          </strong>
          <span>
            {referenceContext.reference_accession}
            {referenceContext.reference_category
              ? ` · ${referenceContext.reference_category}`
              : ""}
            {referenceContext.reference_level
              ? ` · ${referenceContext.reference_level}`
              : ""}
          </span>
        </div>
      ) : null}

      {error ? <div className="notice error-notice">{error}</div> : null}
    </div>
  );
}

function ConstraintField({
  fieldId,
  definition,
  value,
  onChange,
  sources,
}) {
  const type = definition.type || "string";
  const label = definition.label || prettyId(fieldId);
  const description = definition.description || "";
  const unit = definition.unit ? ` (${definition.unit})` : "";

  if (type === "boolean") {
    return (
      <label className="field">
        <span>
          {label}
          {unit}
        </span>
        <select
          value={
            value === true ? "yes" : value === false ? "no" : ""
          }
          onChange={(event) => {
            const selected = event.target.value;
            onChange(
              selected === "yes"
                ? true
                : selected === "no"
                ? false
                : null
            );
          }}
        >
          <option value="">Not specified</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select>
        {description ? <small>{description}</small> : null}
        {sources?.length ? (
          <small>Used by: {sources.join(", ")}</small>
        ) : null}
      </label>
    );
  }

  if (type === "choice" || type === "enum") {
    return (
      <label className="field">
        <span>
          {label}
          {unit}
        </span>
        <select
          value={value ?? ""}
          onChange={(event) =>
            onChange(event.target.value || null)
          }
        >
          <option value="">Not specified</option>
          {(definition.options || []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        {description ? <small>{description}</small> : null}
        {sources?.length ? (
          <small>Used by: {sources.join(", ")}</small>
        ) : null}
      </label>
    );
  }

  return (
    <label className="field">
      <span>
        {label}
        {unit}
      </span>
      <input
        type={type === "integer" || type === "float" ? "number" : "text"}
        step={type === "float" ? "any" : undefined}
        value={value ?? ""}
        onChange={(event) => {
          const raw = event.target.value;

          if (!raw) {
            onChange(null);
            return;
          }

          if (type === "integer") {
            onChange(Number.parseInt(raw, 10));
          } else if (type === "float") {
            onChange(Number.parseFloat(raw));
          } else {
            onChange(raw);
          }
        }}
        placeholder={
          type === "integer"
            ? "Enter an integer"
            : type === "float"
            ? "Enter a number"
            : ""
        }
      />
      {description ? <small>{description}</small> : null}
      {sources?.length ? (
        <small>Used by: {sources.join(", ")}</small>
      ) : null}
    </label>
  );
}

function ConstraintReport({ report, title }) {
  if (!report || report.status === "not_defined") return null;

  return (
    <div className="assessment-report">
      <div className="assessment-report-head">
        <strong>{title}</strong>
        <StatusPill status={report.status} />
      </div>

      {(report.checks || []).map((check, index) => (
        <div className="check-row" key={`${check.id || "check"}-${index}`}>
          <StatusPill status={check.status} />
          <div>
            <strong>{prettyId(check.id || check.kind || "Check")}</strong>
            {check.message ? <p>{check.message}</p> : null}
            {check.observed !== null && check.observed !== undefined ? (
              <small>Observed: {String(check.observed)}</small>
            ) : null}
            {check.expected !== null && check.expected !== undefined ? (
              <small>Expected: {String(check.expected)}</small>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}

function DatasetSuitabilityPanel({
  inspection,
  datasetProfile,
  setDatasetProfile,
  onEvaluate,
  busy,
}) {
  const meta = inspection?.constraint_fields || {};
  const fields = meta.fields || {};
  const entries = Object.entries(fields);

  if (!inspection) return null;

  return (
    <details className="control-details" open={entries.length > 0}>
      <summary>🧪 Dataset profile & suitability</summary>
      <div className="details-body">
        {entries.length === 0 ? (
          <div className="notice info">
            No additional curated dataset-profile fields are required for
            this workflow.
          </div>
        ) : (
          <>
            <p className="muted-copy">
              Fill only the characteristics you know. Missing information
              stays neutral and is not treated as evidence of a mismatch.
            </p>

            <div className="form-grid">
              {entries.map(([fieldId, definition]) => (
                <ConstraintField
                  key={fieldId}
                  fieldId={fieldId}
                  definition={definition}
                  value={datasetProfile[fieldId]}
                  onChange={(value) =>
                    setDatasetProfile((current) => ({
                      ...current,
                      [fieldId]: value,
                    }))
                  }
                  sources={(meta.sources || {})[fieldId]}
                />
              ))}
            </div>

            {meta.conflicts?.length ? (
              <div className="notice warning">
                Some tools define the same dataset field differently.
                OmicsRoute is showing one shared field and preserving the
                conflict for review.
              </div>
            ) : null}

            <button
              className="secondary-button"
              type="button"
              onClick={onEvaluate}
              disabled={busy}
            >
              {busy ? "Evaluating..." : "Evaluate dataset suitability"}
            </button>
          </>
        )}

        <ConstraintReport
          report={inspection.workflow_constraint}
          title="Workflow suitability"
        />
      </div>
    </details>
  );
}

function ComputePanel({
  computeProfile,
  setComputeProfile,
  onApply = null,
  busy = false,
}) {
  const enabled = computeProfile.enabled;

  return (
    <details className="control-details" open>
      <summary>💻 Computer / compute environment</summary>

      <div className="details-body">
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) =>
              setComputeProfile((current) => ({
                ...current,
                enabled: event.target.checked,
              }))
            }
          />
          <div>
            <strong>Use my compute environment when ranking tools</strong>
            <span>
              Practical execution fit stays separate from scientific
              suitability.
            </span>
          </div>
        </label>

        {!enabled ? (
          <div className="notice info">
            Operational re-ranking is off. OmicsRoute keeps the current
            scientific/technical ranking.
          </div>
        ) : (
          <div className="form-grid three">
            <SelectField
              label="Target operating system"
              value={computeProfile.operating_system}
              onChange={(value) =>
                setComputeProfile((current) => ({
                  ...current,
                  operating_system: value,
                }))
              }
              options={["Windows", "Linux", "macOS"]}
            />

            <label className="field">
              <span>RAM (GB)</span>
              <input
                type="number"
                min="1"
                value={computeProfile.ram_gb}
                onChange={(event) =>
                  setComputeProfile((current) => ({
                    ...current,
                    ram_gb: Number(event.target.value),
                  }))
                }
              />
            </label>

            <label className="field">
              <span>CPU cores</span>
              <input
                type="number"
                min="1"
                value={computeProfile.cpu_cores}
                onChange={(event) =>
                  setComputeProfile((current) => ({
                    ...current,
                    cpu_cores: Number(event.target.value),
                  }))
                }
              />
            </label>

            <label className="field">
              <span>Free disk space (GB)</span>
              <input
                type="number"
                min="1"
                value={computeProfile.free_disk_gb}
                onChange={(event) =>
                  setComputeProfile((current) => ({
                    ...current,
                    free_disk_gb: Number(event.target.value),
                  }))
                }
              />
            </label>

            <SelectField
              label="Approximate dataset scale"
              value={computeProfile.dataset_scale}
              onChange={(value) =>
                setComputeProfile((current) => ({
                  ...current,
                  dataset_scale: value,
                }))
              }
              options={["Small", "Moderate", "Large"]}
            />

            <SelectField
              label="Internet / download capacity"
              value={computeProfile.internet}
              onChange={(value) =>
                setComputeProfile((current) => ({
                  ...current,
                  internet: value,
                }))
              }
              options={["Normal", "Limited", "Fast"]}
            />
          </div>
        )}

        {enabled ? (
          <div className="toggle-grid">
            {[
              ["gpu_available", "Compatible GPU available"],
              ["wsl_available", "WSL available"],
              ["container_available", "Docker / containers available"],
              ["hpc_available", "HPC / remote Linux / cloud available"],
              [
                "large_database_ok",
                "Very large reference databases are practical",
              ],
              ["web_services_allowed", "Online analysis services are allowed"],
            ].map(([key, label]) => (
              <label key={key} className="mini-toggle">
                <input
                  type="checkbox"
                  checked={Boolean(computeProfile[key])}
                  onChange={(event) =>
                    setComputeProfile((current) => ({
                      ...current,
                      [key]: event.target.checked,
                    }))
                  }
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
        ) : null}

        <p className="microcopy">
          Resource warnings based on qualitative demand labels are
          heuristics, not universal vendor minimums. Hard blocking is used
          only when a requirement is explicit.
        </p>

        {onApply ? (
          <button
            className="secondary-button"
            type="button"
            onClick={onApply}
            disabled={busy}
          >
            {busy ? "Applying..." : "Re-evaluate workflow with this computer"}
          </button>
        ) : (
          <div className="notice info">
            This computer profile will be used automatically when you build
            the workflow. You can change it at any time.
          </div>
        )}
      </div>
    </details>
  );
}

function DependencyPanel({ dependency }) {
  if (!dependency) return null;

  return (
    <div className={cx("path-card", dependency.valid ? "path-good" : "path-bad")}>
      <div>
        <strong>
          {dependency.valid
            ? "Workflow path is technically complete."
            : "Workflow path is incomplete."}
        </strong>
        <p>
          {dependency.valid
            ? "An executable artifact path exists through the selected route."
            : "One or more required artifacts cannot currently reach a downstream step."}
        </p>
      </div>

      <details>
        <summary>Technical details</summary>
        <div className="technical-details">
          {(dependency.initial_artifacts_labeled || []).length ? (
            <>
              <strong>Initial / user-supplied artifacts</strong>
              <ul>
                {dependency.initial_artifacts_labeled.map((item) => (
                  <li key={item.id}>
                    {item.is_collection ? "🧺 " : ""}
                    {item.label}
                    {item.is_collection ? " (collection)" : ""}
                  </li>
                ))}
              </ul>
            </>
          ) : null}

          {(dependency.steps || []).map((step) => (
            <div className="technical-step" key={step.step_number}>
              <div>
                <StatusPill
                  status={
                    step.status === "ok"
                      ? "pass"
                      : step.status === "blocked"
                      ? "block"
                      : "warning"
                  }
                />
                <strong>
                  {step.step_number}. {step.name}
                </strong>
              </div>

              {step.mode === "parallel" ? (
                <small>
                  Successful branches: {step.successful_candidate_count}/
                  {step.required_candidate_count} required
                </small>
              ) : null}

              {(step.blocked_tools || []).map((item) => (
                <small key={item.tool}>
                  {item.tool}: missing {(item.missing || []).join(", ")}
                </small>
              ))}
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

function ReferenceGuidancePanel({
  referenceData,
  onScopeChange,
}) {
  const options = referenceData?.scope_options || [];
  const guidance = referenceData?.guidance;

  if (!options.length || !guidance) return null;

  return (
    <details className="control-details" open>
      <summary>🧬 Reference / database guidance</summary>

      <div className="details-body">
        <SelectField
          label={referenceData.scope_label || "Taxonomic scope"}
          value={referenceData.selected_scope || ""}
          onChange={onScopeChange}
          options={options.map((item) => ({
            value: item.id,
            label: item.label,
          }))}
        />

        <div className="guidance-grid">
          <div>
            <span>Route status</span>
            <strong>{prettyId(guidance.status)}</strong>
          </div>
          {guidance.preferred_database ? (
            <div>
              <span>Preferred reference</span>
              <strong>{guidance.preferred_database}</strong>
            </div>
          ) : null}
        </div>

        {guidance.route_recommendation ? (
          <div className="notice info">
            <strong>For this route</strong>
            <p>{guidance.route_recommendation}</p>
          </div>
        ) : null}

        {guidance.alternatives?.length ? (
          <div className="mini-list">
            <strong>Alternatives</strong>
            {guidance.alternatives.map((item) => (
              <span key={item}>• {item}</span>
            ))}
          </div>
        ) : null}

        {guidance.important?.length ? (
          <div className="mini-list">
            <strong>Important</strong>
            {guidance.important.map((item) => (
              <span key={item}>• {item}</span>
            ))}
          </div>
        ) : null}

        {guidance.avoid?.length ? (
          <div className="mini-list warning-list">
            <strong>Avoid</strong>
            {guidance.avoid.map((item) => (
              <span key={item}>• {item}</span>
            ))}
          </div>
        ) : null}
      </div>
    </details>
  );
}

function EvidencePanel({ evidence }) {
  if (!evidence) return null;

  if (evidence.loading) {
    return <div className="notice info">Searching literature sources...</div>;
  }

  if (evidence.error && !evidence.data) {
    return <div className="notice error-notice">{evidence.error}</div>;
  }

  const data = evidence.data;
  const summary = data?.summary || {};

  return (
    <div className="evidence-panel">
      <div className="evidence-head">
        <div>
          <span>Literature support</span>
          <strong>{summary.total ?? 0}/100</strong>
        </div>
        <small>
          Separate confidence signal — it does not overwrite the OmicsRoute
          recommendation score.
        </small>
      </div>

      <div className="evidence-metrics">
        <Metric label="Benchmark" value={summary.benchmark_count ?? 0} />
        <Metric label="Method" value={summary.method_count ?? 0} />
        <Metric label="Review" value={summary.review_count ?? 0} />
        <Metric label="Application" value={summary.application_count ?? 0} />
      </div>

      {data.partial_errors?.length ? (
        <div className="notice warning">
          Partial source warnings: {data.partial_errors.join(" · ")}
        </div>
      ) : null}

      <div className="paper-list">
        {(data.papers || []).slice(0, 8).map((paper, index) => (
          <article key={`${paper.doi || paper.pmid || paper.title}-${index}`}>
            <div>
              <StatusPill status="neutral">
                {paper.evidence_label || prettyId(paper.evidence_category)}
              </StatusPill>
              {paper.year ? <span>{paper.year}</span> : null}
              {paper.cited_by_count ? (
                <span>{paper.cited_by_count} citations</span>
              ) : null}
            </div>
            <strong>{paper.title || "Untitled publication"}</strong>
            <small>
              {(paper.source_providers || []).join(", ")}
            </small>
            {paper.url ? (
              <a href={paper.url} target="_blank" rel="noreferrer">
                Open publication ↗
              </a>
            ) : paper.doi ? (
              <a
                href={`https://doi.org/${paper.doi}`}
                target="_blank"
                rel="noreferrer"
              >
                DOI ↗
              </a>
            ) : null}
          </article>
        ))}
      </div>
    </div>
  );
}

function WorkflowLiteraturePanel({ research }) {
  if (!research) return null;

  if (research.loading) {
    return (
      <section className="workflow-literature">
        <div className="workflow-literature-head">
          <div>
            <span className="section-number">Literature structure check</span>
            <h3>Researching workflow-level evidence...</h3>
          </div>
          <StatusPill status="needs_input">Searching</StatusPill>
        </div>
        <p className="muted-copy">
          OmicsRoute is checking OpenAlex and Europe PMC for publications
          relevant to this biological goal and data context. The workflow
          result above remains usable while this research runs.
        </p>
      </section>
    );
  }

  if (research.error && !research.data) {
    return (
      <section className="workflow-literature">
        <div className="workflow-literature-head">
          <div>
            <span className="section-number">Literature structure check</span>
            <h3>Workflow literature could not be loaded</h3>
          </div>
          <StatusPill status="warning">Unavailable</StatusPill>
        </div>
        <div className="notice warning">{research.error}</div>
      </section>
    );
  }

  const data = research.data || {};
  const supported = data.planned_operations_with_literature_signal || 0;
  const planned = data.planned_operation_count || 0;
  const fraction =
    data.planner_alignment_fraction === null ||
    data.planner_alignment_fraction === undefined
      ? "—"
      : `${Math.round(Number(data.planner_alignment_fraction) * 100)}%`;

  const plannedRows = (data.operation_support || []).filter(
    (item) => item.planned
  );

  const candidates = data.contextual_candidate_operations || [];

  return (
    <section className="workflow-literature">
      <div className="workflow-literature-head">
        <div>
          <span className="section-number">
            Literature-supported workflow structure
          </span>
          <h3>How much of this route is visible in retrieved literature?</h3>
        </div>
        <StatusPill status="pass">Researched</StatusPill>
      </div>

      <p className="workflow-literature-copy">
        This is a workflow-level evidence layer, separate from tool-level
        evidence. It checks which analysis operations recur in publications
        for the selected context. Literature co-occurrence does not infer
        executable step order; artifact and dependency rules still control
        the technical route.
      </p>

      <div className="literature-metrics">
        <Metric label="Retrieved papers" value={data.paper_count || 0} />
        <Metric label="Planned operations" value={planned} />
        <Metric label="With literature signal" value={supported} />
        <Metric label="Operation evidence coverage" value={fraction} />
      </div>

      {data.partial_errors?.length ? (
        <div className="notice warning">
          Some literature sources returned warnings:{" "}
          {data.partial_errors.join(" · ")}
        </div>
      ) : null}

      {data.targeted_followup_triggered ? (
        <div className="notice info">
          OmicsRoute ran targeted follow-up searches for planned operations
          that had zero or limited signal in the broad workflow search.
        </div>
      ) : null}

      <div className="literature-operation-list">
        <strong>Planned operations</strong>

        {!plannedRows.length ? (
          <span className="muted-copy">
            No operation-level support rows were returned.
          </span>
        ) : (
          plannedRows.map((item) => (
            <div
              className="literature-operation-row"
              key={item.operation}
            >
              <div>
                <span
                  className={cx(
                    "literature-dot",
                    item.supporting_paper_count > 0
                      ? "literature-dot-supported"
                      : "literature-dot-missing"
                  )}
                />
                <div>
                  <strong>{item.label}</strong>
                  <small>
                    {item.supporting_paper_count > 0
                      ? `${item.supporting_paper_count} publication${
                          item.supporting_paper_count === 1 ? "" : "s"
                        } with a matching title/abstract signal`
                      : "No matching signal in the retrieved titles/abstracts"}
                  </small>
                </div>
              </div>

              <StatusPill
                status={
                  item.confidence === "strong" ||
                  item.confidence === "moderate"
                    ? "pass"
                    : item.confidence === "limited"
                    ? "warning"
                    : "not_defined"
                }
              >
                {item.confidence === "none"
                  ? "No signal retrieved"
                  : `${prettyId(item.confidence)} signal`}
              </StatusPill>
            </div>
          ))
        )}
      </div>

      <div className="literature-candidates">
        <strong>Literature signals not currently in route</strong>

        {!candidates.length ? (
          <span className="muted-copy">
            No repeated contextual operation signal crossed the current
            threshold.
          </span>
        ) : (
          candidates.map((item) => (
            <div key={item.operation} className="literature-candidate">
              <div>
                <strong>{item.label}</strong>
                <span>
                  Seen in {item.supporting_paper_count} retrieved
                  publications · {prettyId(item.confidence)} support
                </span>
              </div>
              <StatusPill status="warning">Needs validation</StatusPill>
            </div>
          ))
        )}

        <small>
          These are research leads, not automatically inserted steps. A
          candidate must first pass artifact/I/O, tool-capability and
          context-specific validation. Zero title/abstract matches also do not
          mean that an existing planned step is unnecessary.
        </small>
      </div>

      <details className="literature-papers">
        <summary>View retrieved publications and search queries</summary>
        <div>
          {(data.queries || []).length ? (
            <div className="mini-list">
              <strong>Search queries</strong>
              {(data.queries || []).map((query) => (
                <span key={query}>• {query}</span>
              ))}
            </div>
          ) : null}

          <div className="paper-list">
            {(data.papers || []).slice(0, 12).map((paper, index) => (
              <article
                key={`${paper.doi || paper.pmid || paper.title}-${index}`}
              >
                <div>
                  {paper.year ? <span>{paper.year}</span> : null}
                  {(paper.source_providers || []).length ? (
                    <span>{paper.source_providers.join(", ")}</span>
                  ) : null}
                </div>
                <strong>{paper.title || "Untitled publication"}</strong>
                {paper.journal ? <small>{paper.journal}</small> : null}
                {paper.url ? (
                  <a href={paper.url} target="_blank" rel="noreferrer">
                    Open publication ↗
                  </a>
                ) : null}
              </article>
            ))}
          </div>
        </div>
      </details>
    </section>
  );
}


function BioToolsPanel({ info }) {
  if (!info) return null;

  if (info.loading) {
    return <div className="notice info">Loading bio.tools metadata...</div>;
  }

  if (info.error && !info.data) {
    return <div className="notice error-notice">{info.error}</div>;
  }

  const record = info.data?.record;

  if (!record) {
    return (
      <div className="notice info">
        No matching bio.tools record was returned.
      </div>
    );
  }

  return (
    <div className="registry-panel">
      <strong>Live metadata from bio.tools</strong>
      {record.description ? <p>{record.description}</p> : null}
      <div className="tag-row">
        {(record.operations || []).slice(0, 8).map((item) => (
          <span key={item}>{item}</span>
        ))}
        {(record.topics || []).slice(0, 6).map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
      {record.biotools_url ? (
        <a href={record.biotools_url} target="_blank" rel="noreferrer">
          Open bio.tools record ↗
        </a>
      ) : null}
    </div>
  );
}

function ToolCard({
  tool,
  operation,
  stepMode,
  evidence,
  biotools,
  onEvidence,
  onBioTools,
}) {
  const [open, setOpen] = useState(false);
  const assessment = tool._assessment || {};
  const score = tool.score || {};
  const dependency = assessment.dependency || {};
  const constraint = assessment.constraint || {};
  const operational = assessment.operational || {};
  const rank = assessment.rank;

  const isParallel = stepMode === "parallel";
  const roleLabel = isParallel
    ? "Parallel branch"
    : rank === 1
    ? "Top-ranked"
    : rank
    ? `Rank ${rank}`
    : "Candidate";

  return (
    <div
      className={cx(
        "tool-card",
        !isParallel && rank === 1 && "tool-card-primary"
      )}
    >
      <button
        className="tool-summary"
        type="button"
        onClick={() => setOpen((current) => !current)}
      >
        <div className="tool-summary-main">
          <div className="tool-title-line">
            <strong>{tool.name || tool.id}</strong>
            <span className={cx("role-badge", rank === 1 && "role-top")}>
              {roleLabel}
            </span>
          </div>

          <div className="tool-status-line">
            <StatusPill status={dependency.status} />
            <StatusPill status={constraint.status} />
            {assessment.compute_profile_enabled ? (
              <StatusPill status={operational.status} />
            ) : null}
          </div>
        </div>

        <div className="tool-summary-side">
          <div className="score-badge">
            <strong>{Number(score.total || 0)}</strong>
            <span>/100</span>
          </div>
          <span>{open ? "Hide" : "Details"}</span>
        </div>
      </button>

      {open ? (
        <div className="tool-detail">
          {tool.description ? <p>{tool.description}</p> : null}

          <div className="score-panel">
            <div className="score-total">
              <span>OmicsRoute recommendation score</span>
              <strong>{Number(score.total || 0)}/100</strong>
            </div>

            <ScoreBar
              label="Scientific suitability"
              value={score.scientific_fit}
              max={score.scientific_fit_max || 60}
            />
            <ScoreBar
              label="Maintenance"
              value={score.maintenance}
              max={score.maintenance_max || 15}
            />
            <ScoreBar
              label="Reproducibility"
              value={score.reproducibility}
              max={score.reproducibility_max || 15}
            />
            <ScoreBar
              label="Community"
              value={score.community}
              max={score.community_max || 10}
            />

            <p className="microcopy">
              Literature evidence, dataset constraints and operational
              feasibility remain separate layers and do not numerically hide
              a scientific mismatch.
            </p>
          </div>

          <div className="detail-grid">
            <div>
              <span>Scientific fit</span>
              <strong>
                {score.scientific_fit_display ||
                  prettyId(score.scientific_fit_label)}
              </strong>
            </div>
            <div>
              <span>Dataset compatibility</span>
              <strong>{tool.compatible === false ? "Check required" : "Pass"}</strong>
            </div>
            <div>
              <span>Input</span>
              <strong>
                {Array.isArray(tool.input)
                  ? tool.input.join(", ")
                  : tool.input || "Not specified"}
              </strong>
            </div>
            <div>
              <span>Output</span>
              <strong>
                {Array.isArray(tool.output)
                  ? tool.output.join(", ")
                  : tool.output || "Not specified"}
              </strong>
            </div>
          </div>

          {dependency.status === "blocked" ? (
            <div className="notice error-notice">
              <strong>Technical prerequisite artifact is missing.</strong>
              {(dependency.missing || []).map((item) => (
                <span key={item.id}>• {item.label}</span>
              ))}
            </div>
          ) : dependency.status === "unknown" ? (
            <div className="notice warning">
              Tool I/O dependency metadata is not fully defined.
            </div>
          ) : null}

          <ConstraintReport
            report={constraint}
            title="Dataset suitability"
          />

          {assessment.compute_profile_enabled &&
          operational.status !== "not_evaluated" ? (
            <div className="assessment-report">
              <div className="assessment-report-head">
                <strong>Operational feasibility</strong>
                <StatusPill status={operational.status} />
              </div>

              {(operational.blockers || []).map((item) => (
                <p key={item}>⛔ {item}</p>
              ))}
              {(operational.warnings || []).map((item) => (
                <p key={item}>⚠️ {item}</p>
              ))}
              {(operational.reasons || []).map((item) => (
                <p key={item}>• {item}</p>
              ))}
            </div>
          ) : null}

          <div className="tag-row">
            {tool.bioconda ? <span>Bioconda</span> : null}
            {tool.container ? <span>Container</span> : null}
            {tool.galaxy ? <span>Galaxy</span> : null}
            {tool.nfcore ? <span>nf-core</span> : null}
          </div>

          <div className="tool-actions">
            {tool.official_docs ? (
              <a href={tool.official_docs} target="_blank" rel="noreferrer">
                Official documentation ↗
              </a>
            ) : null}
            {tool.repository ? (
              <a href={tool.repository} target="_blank" rel="noreferrer">
                Repository ↗
              </a>
            ) : null}
            <button type="button" onClick={onEvidence}>
              📚 Search literature evidence
            </button>
            <button type="button" onClick={onBioTools}>
              🌐 Load live bio.tools metadata
            </button>
          </div>

          <EvidencePanel evidence={evidence} />
          <BioToolsPanel info={biotools} />
        </div>
      ) : null}
    </div>
  );
}

function DecisionPointsPanel({ points }) {
  if (!points?.length) return null;

  return (
    <section className="decision-points">
      <div className="decision-points-head">
        <div>
          <span className="section-number">Context-dependent decisions</span>
          <h3>Steps that should not be applied blindly</h3>
        </div>
        <StatusPill status="needs_input">Review context</StatusPill>
      </div>

      <p className="muted-copy">
        These checks can materially change a hybrid genome workflow, but they
        are not universal mandatory steps. OmicsRoute keeps them explicit
        instead of silently forcing the same recipe onto every genome.
      </p>

      <div className="decision-point-list">
        {points.map((point) => (
          <article key={point.id} className="decision-point">
            <div className="decision-point-title">
              <strong>{point.title}</strong>
              <StatusPill
                status={
                  point.status === "needs_input"
                    ? "needs_input"
                    : point.status === "decision_gate"
                    ? "warning"
                    : "not_defined"
                }
              >
                {prettyId(point.status)}
              </StatusPill>
            </div>

            {point.when ? <p><strong>When:</strong> {point.when}</p> : null}
            {point.why ? <p><strong>Why:</strong> {point.why}</p> : null}

            {point.suggested_tools?.length ? (
              <div className="tag-row">
                {point.suggested_tools.map((tool) => (
                  <span key={tool}>{tool}</span>
                ))}
              </div>
            ) : null}

            {(point.evidence || []).map((item) => (
              <a
                key={item.url || item.label}
                href={item.url}
                target="_blank"
                rel="noreferrer"
              >
                {item.label || "Documentation"} ↗
              </a>
            ))}
          </article>
        ))}
      </div>
    </section>
  );
}


function RecoveryPanel({ recovery }) {
  if (!recovery) return null;

  if (recovery.status === "continue") {
    return (
      <div className="recovery recovery-good">
        <strong>Recommended next action</strong>
        <p>{recovery.message}</p>
        {recovery.ready_tools?.length ? (
          <span>Ready: {recovery.ready_tools.join(", ")}</span>
        ) : null}
      </div>
    );
  }

  return (
    <div className="recovery recovery-bad">
      <strong>No ready candidate remains for this step</strong>
      <p>{recovery.message}</p>

      {recovery.strategies?.length ? (
        <div className="mini-list">
          <strong>Alternative workflow strategies</strong>
          {recovery.strategies.map((item) => (
            <span key={item.id || item.name}>
              • {item.name || item.id}
              {item.description ? ` — ${item.description}` : ""}
            </span>
          ))}
        </div>
      ) : null}

      {recovery.remediations?.length ? (
        <div className="mini-list">
          <strong>Keep the current strategy: fix its requirements</strong>
          {recovery.remediations.map((item, index) => (
            <span key={`${item.title || "fix"}-${index}`}>
              • {item.message}
              {item.fallback_note ? ` — ${item.fallback_note}` : ""}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function DiscoveryPanel({
  step,
  index,
  result,
  onResearch,
}) {
  const [depth, setDepth] = useState("Standard");

  return (
    <details className="discovery">
      <summary>🔎 Advanced registry search for uncurated alternatives</summary>

      <div className="details-body">
        <p className="muted-copy">
          Core routes are curated above. Use this only when you want
          OmicsRoute to search beyond the curated ranking.
        </p>

        <div className="inline-form compact">
          <SelectField
            label="Discovery search depth"
            value={depth}
            onChange={setDepth}
            options={["Standard", "Deep"]}
          />

          <button
            className="secondary-button align-end"
            type="button"
            onClick={() => onResearch(index, step, depth)}
            disabled={result?.loading}
          >
            {result?.loading ? "Researching..." : "Research alternatives"}
          </button>
        </div>

        {result?.error ? (
          <div className="notice error-notice">{result.error}</div>
        ) : null}

        {result?.data ? (
          <div className="research-results">
            <div className="evidence-metrics">
              <Metric
                label="Verified direct"
                value={result.data.compatible_count || 0}
              />
              <Metric
                label="Related routes"
                value={result.data.related_count || 0}
              />
              <Metric
                label="Unverified leads"
                value={result.data.unverified_count || 0}
              />
              <Metric
                label="bio.tools hits"
                value={result.data.registry_candidate_count || 0}
              />
            </div>

            <ResearchGroup
              title="✅ Verified direct alternatives"
              items={result.data.compatible_results || []}
            />
            <ResearchGroup
              title="🧭 Related, but not a drop-in replacement"
              items={result.data.related_results || []}
            />
            <ResearchGroup
              title="🗂️ Unverified bio.tools leads"
              items={result.data.unverified_results || []}
            />
          </div>
        ) : null}
      </div>
    </details>
  );
}

function ResearchGroup({ title, items }) {
  return (
    <div className="research-group">
      <strong>{title}</strong>

      {!items.length ? (
        <span className="muted-copy">No results in this category.</span>
      ) : (
        items.slice(0, 12).map((item, index) => {
          const evaluation = item.capability_evaluation || {};

          return (
            <article key={`${item.name || "candidate"}-${index}`}>
              <strong>{item.name || "Unnamed resource"}</strong>
              {(evaluation.reasons || []).map((reason) => (
                <p key={reason}>• {reason}</p>
              ))}
              {item.description ? <p>{item.description}</p> : null}
              {item.biotools_url ? (
                <a
                  href={item.biotools_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  bio.tools record ↗
                </a>
              ) : null}
            </article>
          );
        })
      )}
    </div>
  );
}

function CoveragePanel({ coverage, loading, onAudit }) {
  return (
    <details className="top-details">
      <summary>📚 Catalogue coverage & validation</summary>

      <div className="top-details-body">
        {!coverage ? (
          <div className="notice info">Coverage data is loading...</div>
        ) : (
          <>
            <div className="evidence-metrics">
              {coverage.dependency_audit ? (
                <>
                  <Metric
                    label="Dependency-valid goals"
                    value={coverage.validated}
                  />
                  <Metric
                    label="Broken / incomplete"
                    value={coverage.broken}
                  />
                  <Metric label="Planned" value={coverage.planned} />
                  <Metric
                    label="Validated coverage"
                    value={`${coverage.percentage}%`}
                  />
                </>
              ) : (
                <>
                  <Metric
                    label="Implemented goals"
                    value={coverage.supported}
                  />
                  <Metric label="Catalogue goals" value={coverage.total} />
                  <Metric
                    label="Implemented coverage"
                    value={`${coverage.percentage}%`}
                  />
                </>
              )}
            </div>

            <button
              className="secondary-button"
              type="button"
              onClick={onAudit}
              disabled={loading}
            >
              {loading
                ? "Running dependency audit..."
                : "Run / refresh dependency coverage audit"}
            </button>

            <div className="coverage-families">
              {(coverage.families || []).map((family) => (
                <details key={family.id}>
                  <summary>
                    {family.label} —{" "}
                    {coverage.dependency_audit
                      ? `${family.validated_count || 0}/${
                          family.total_count
                        } dependency-valid`
                      : `${family.supported_count}/${family.total_count} implemented`}
                  </summary>

                  <div>
                    {family.description ? <p>{family.description}</p> : null}

                    {(family.goals || []).map((goal) => (
                      <span key={goal.id || goal.label}>
                        {coverage.dependency_audit
                          ? goal.dependency_status === "valid"
                            ? "✅"
                            : goal.dependency_status === "broken"
                            ? "⚠️"
                            : "⏳"
                          : goal.supported
                          ? "✅"
                          : "⏳"}{" "}
                        {goal.label}
                      </span>
                    ))}
                  </div>
                </details>
              ))}
            </div>
          </>
        )}
      </div>
    </details>
  );
}

function AboutPanel() {
  return (
    <details className="top-details">
      <summary>ℹ️ About OmicsRoute & methodology</summary>

      <div className="top-details-body about-grid">
        <section>
          <span className="section-number">About</span>
          <h3>OmicsRoute v0.1.0-beta.1</h3>
          <p>
            OmicsRoute is a bioinformatics workflow planning and
            decision-support system. It recommends workflows and candidate
            tools; it does not execute the underlying bioinformatics
            software.
          </p>
        </section>

        <section>
          <span className="section-number">Methodology</span>
          <h3>How recommendations are formed</h3>
          <p>
            Workflow context → scientific fit → dependency validation →
            dataset and operational constraints → evidence and fallback
            logic.
          </p>
          <p>
            Literature evidence can refine otherwise comparable
            candidates, but it does not override hard technical or dataset
            blocks.
          </p>
        </section>

        <section>
          <span className="section-number">Interpretation</span>
          <h3>How to use the output</h3>
          <p>
            Recommendation scores are OmicsRoute support scores within the
            curated catalogue; they are not universal measures of tool
            quality.
          </p>
          <p>
            The current benchmark is an internal curated benchmark for
            regression and recommendation validation, not an independent
            external gold standard.
          </p>
        </section>
      </div>
    </details>
  );
}

export default function HomePage() {
  const [apiState, setApiState] = useState("checking");
  const [globalError, setGlobalError] = useState("");

  const [sampleTypes, setSampleTypes] = useState([]);
  const [sampleType, setSampleType] = useState("");

  const [dataStates, setDataStates] = useState([]);
  const [dataState, setDataState] = useState("");

  const [sequencingOptions, setSequencingOptions] = useState([]);
  const [sequencing, setSequencing] = useState("");

  const [readTypes, setReadTypes] = useState([]);
  const [readType, setReadType] = useState("");

  const [referenceContext, setReferenceContext] = useState(null);

  const [goals, setGoals] = useState([]);
  const [goal, setGoal] = useState("");

  const [strategies, setStrategies] = useState([]);
  const [strategyId, setStrategyId] = useState("");

  const [inspection, setInspection] = useState(null);
  const [workflowResearch, setWorkflowResearch] = useState(null);
  const [datasetProfile, setDatasetProfile] = useState({});
  const [computeProfile, setComputeProfile] = useState(DEFAULT_COMPUTE);
  const [workflowBusy, setWorkflowBusy] = useState(false);

  const plannerRef = useRef(null);
  const resultRef = useRef(null);

  const [evidenceByKey, setEvidenceByKey] = useState({});
  const [biotoolsByKey, setBiotoolsByKey] = useState({});
  const [discoveryByStep, setDiscoveryByStep] = useState({});

  const [coverage, setCoverage] = useState(null);
  const [coverageLoading, setCoverageLoading] = useState(false);

  const selectedDataState = useMemo(
    () => dataStates.find((item) => item.id === dataState),
    [dataStates, dataState]
  );

  const referenceSupported = Boolean(
    selectedDataState?.supports_reference_finder
  );

  const currentGoal = useMemo(
    () => goals.find((item) => item.id === goal),
    [goals, goal]
  );

  const isRawReads = dataState === RAW_READS;

  useEffect(() => {
    async function bootstrap() {
      try {
        await getHealth();
        const [samples, coveragePayload] = await Promise.all([
          getSampleTypes(),
          getCoverage(false),
        ]);

        setSampleTypes(samples.sample_types || []);
        setCoverage(coveragePayload);
        setApiState("online");
      } catch (err) {
        setApiState("offline");
        setGlobalError(err.message);
      }
    }

    bootstrap();

    if (typeof navigator !== "undefined") {
      const platform = navigator.userAgent.toLowerCase();
      const detectedOs = platform.includes("win")
        ? "Windows"
        : platform.includes("mac")
        ? "macOS"
        : "Linux";

      setComputeProfile((current) => ({
        ...current,
        operating_system: detectedOs,
        cpu_cores:
          navigator.hardwareConcurrency &&
          Number.isFinite(navigator.hardwareConcurrency)
            ? navigator.hardwareConcurrency
            : current.cpu_cores,
      }));
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

    try {
      const saved = window.localStorage.getItem(
        "omicsroute.computeProfile"
      );

      if (!saved) return;

      const parsed = JSON.parse(saved);

      if (parsed && typeof parsed === "object") {
        setComputeProfile((current) => ({
          ...current,
          ...parsed,
        }));
      }
    } catch {
      // Ignore stale or malformed local preferences.
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

    try {
      window.localStorage.setItem(
        "omicsroute.computeProfile",
        JSON.stringify(computeProfile)
      );
    } catch {
      // Local storage is optional.
    }
  }, [computeProfile]);

  useEffect(() => {
    setDataStates([]);
    setDataState("");
    setSequencingOptions([]);
    setSequencing("");
    setReadTypes([]);
    setReadType("");
    setReferenceContext(null);
    setGoals([]);
    setGoal("");
    setStrategies([]);
    setStrategyId("");
    resetWorkflowState();

    if (!sampleType) return;

    Promise.all([
      getDataStates(sampleType),
      getSequencingOptions(sampleType),
    ])
      .then(([states, seqs]) => {
        setDataStates(states.data_states || []);
        setSequencingOptions(seqs.sequencing_options || []);
      })
      .catch((err) => setGlobalError(err.message));
  }, [sampleType]);

  useEffect(() => {
    setSequencing("");
    setReadTypes([]);
    setReadType("");
    setGoals([]);
    setGoal("");
    setStrategies([]);
    setStrategyId("");
    resetWorkflowState();
  }, [dataState]);

  useEffect(() => {
    setReadTypes([]);
    setReadType("");
    setGoals([]);
    setGoal("");
    setStrategies([]);
    setStrategyId("");
    resetWorkflowState();

    if (!sampleType || !sequencing || !isRawReads) return;

    getReadTypes(sampleType, sequencing)
      .then((payload) => setReadTypes(payload.read_types || []))
      .catch((err) => setGlobalError(err.message));
  }, [sampleType, sequencing, isRawReads]);

  useEffect(() => {
    setGoals([]);
    setGoal("");
    setStrategies([]);
    setStrategyId("");
    resetWorkflowState();

    if (!sampleType || !dataState) return;
    if (isRawReads && (!sequencing || !readType)) return;

    getGoals({
      sample_type: sampleType,
      data_state: dataState,
      sequencing: isRawReads ? sequencing : null,
      read_type: isRawReads ? readType : null,
      reference_context: referenceContext,
    })
      .then((payload) => setGoals(payload.goals || []))
      .catch((err) => setGlobalError(err.message));
  }, [
    sampleType,
    dataState,
    sequencing,
    readType,
    isRawReads,
    referenceContext,
  ]);

  useEffect(() => {
    setStrategies([]);
    setStrategyId("");
    resetWorkflowState();

    if (!goal || !currentGoal?.selectable) return;

    getStrategies({
      sample_type: sampleType,
      data_state: dataState,
      sequencing: isRawReads ? sequencing : null,
      read_type: isRawReads ? readType : null,
      goal,
      reference_context: referenceContext,
    })
      .then((payload) => {
        const rows = payload.strategies || [];
        setStrategies(rows);
        if (rows.length === 1) setStrategyId(rows[0].id);
      })
      .catch((err) => setGlobalError(err.message));
  }, [
    goal,
    currentGoal,
    sampleType,
    dataState,
    sequencing,
    readType,
    isRawReads,
    referenceContext,
  ]);

  function resetWorkflowState() {
    setInspection(null);
    setWorkflowResearch(null);
    setDatasetProfile({});
    setEvidenceByKey({});
    setBiotoolsByKey({});
    setDiscoveryByStep({});
  }

  function resetPlanner() {
    setSampleType("");
    setDataStates([]);
    setDataState("");
    setSequencingOptions([]);
    setSequencing("");
    setReadTypes([]);
    setReadType("");
    setReferenceContext(null);
    setGoals([]);
    setGoal("");
    setStrategies([]);
    setStrategyId("");
    resetWorkflowState();
    setGlobalError("");

    if (typeof window !== "undefined") {
      window.requestAnimationFrame(() => {
        plannerRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      });
    }
  }

  function inspectionPayload(overrides = {}) {
    return {
      sample_type: sampleType,
      data_state: dataState,
      sequencing: isRawReads ? sequencing : null,
      read_type: isRawReads ? readType : null,
      goal,
      workflow_id: strategyId,
      reference_context: referenceContext,
      dataset_profile:
        overrides.dataset_profile !== undefined
          ? overrides.dataset_profile
          : datasetProfile,
      compute_profile:
        overrides.compute_profile !== undefined
          ? overrides.compute_profile
          : computeProfile,
      scope_id:
        overrides.scope_id !== undefined
          ? overrides.scope_id
          : inspection?.reference_guidance?.selected_scope || null,
    };
  }

  function workflowResearchPayload() {
    return {
      sample_type: sampleType,
      data_state: dataState,
      sequencing: isRawReads ? sequencing : null,
      read_type: isRawReads ? readType : null,
      goal,
      workflow_id: strategyId,
      reference_context: referenceContext,
      compute_profile: computeProfile,
      years: 10,
    };
  }

  async function loadWorkflowResearch() {
    if (!goal || !strategyId) return;

    setWorkflowResearch({ loading: true });

    try {
      const data = await researchWorkflow(
        workflowResearchPayload()
      );

      setWorkflowResearch({
        loading: false,
        data,
      });
    } catch (err) {
      setWorkflowResearch({
        loading: false,
        error: err.message,
      });
    }
  }


  async function handleBuild() {
    if (!goal || !strategyId) return;
    setWorkflowBusy(true);
    setGlobalError("");

    try {
      const result = await inspectWorkflow(inspectionPayload());
      setInspection(result);

      // Workflow-level literature research is intentionally non-blocking.
      // The technical plan appears immediately; literature structure support
      // is loaded as a separate evidence layer.
      void loadWorkflowResearch();

      if (typeof window !== "undefined") {
        window.requestAnimationFrame(() => {
          resultRef.current?.scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        });
      }
    } catch (err) {
      setGlobalError(err.message);
    } finally {
      setWorkflowBusy(false);
    }
  }

  async function refreshInspection(overrides = {}) {
    if (!inspection) return;
    setWorkflowBusy(true);
    setGlobalError("");

    try {
      const result = await inspectWorkflow(
        inspectionPayload(overrides)
      );
      setInspection(result);
    } catch (err) {
      setGlobalError(err.message);
    } finally {
      setWorkflowBusy(false);
    }
  }

  async function handleScopeChange(nextScope) {
    if (!inspection?.workflow) return;

    try {
      const result = await getReferenceGuidance(
        goal,
        inspection.workflow.id,
        nextScope
      );

      setInspection((current) => ({
        ...current,
        reference_guidance: result,
      }));
    } catch (err) {
      setGlobalError(err.message);
    }
  }

  async function loadEvidence(key, tool, operation) {
    setEvidenceByKey((current) => ({
      ...current,
      [key]: { loading: true },
    }));

    try {
      const data = await getToolEvidence(
        tool.name || tool.id,
        operation
      );

      setEvidenceByKey((current) => ({
        ...current,
        [key]: { loading: false, data },
      }));
    } catch (err) {
      setEvidenceByKey((current) => ({
        ...current,
        [key]: { loading: false, error: err.message },
      }));
    }
  }

  async function loadBioTools(key, tool) {
    setBiotoolsByKey((current) => ({
      ...current,
      [key]: { loading: true },
    }));

    try {
      const data = await getBioTools(tool.name || tool.id);

      setBiotoolsByKey((current) => ({
        ...current,
        [key]: { loading: false, data },
      }));
    } catch (err) {
      setBiotoolsByKey((current) => ({
        ...current,
        [key]: { loading: false, error: err.message },
      }));
    }
  }

  async function researchStep(index, step, depth) {
    setDiscoveryByStep((current) => ({
      ...current,
      [index]: { loading: true },
    }));

    try {
      const data = await researchAlternatives({
        operation: step.operation,
        context: step.context || {},
        curated_tools: (step.tools || []).map(
          (tool) => tool.name || tool.id
        ),
        depth,
      });

      setDiscoveryByStep((current) => ({
        ...current,
        [index]: { loading: false, data },
      }));
    } catch (err) {
      setDiscoveryByStep((current) => ({
        ...current,
        [index]: { loading: false, error: err.message },
      }));
    }
  }

  async function runCoverageAudit() {
    setCoverageLoading(true);
    try {
      const result = await getCoverage(true);
      setCoverage(result);
    } catch (err) {
      setGlobalError(err.message);
    } finally {
      setCoverageLoading(false);
    }
  }

  const workflow = inspection?.workflow;
  const overview = inspection?.overview || {};

  const contextReady = Boolean(
    sampleType &&
      dataState &&
      (!isRawReads || (sequencing && readType))
  );

  const progressChecks = [
    contextReady,
    Boolean(goal),
    Boolean(strategyId),
    Boolean(workflow),
  ];

  const progressCount = progressChecks.filter(Boolean).length;
  const progressPercent = (progressCount / progressChecks.length) * 100;

  return (
    <main className="shell">
      {/* OMICSROUTE_PUBLIC_BETA_USABILITY_V1 */}
      <header className="site-header">
        <a className="site-brand" href="#" aria-label="OmicsRoute home">
          <span className="brand-mark">OR</span>
          <span>
            OmicsRoute
            <small>Public beta</small>
          </span>
        </a>

        <nav className="site-nav" aria-label="Primary navigation">
          <a href="#planner">Planner</a>
          <a href="#how-it-works">How it works</a>
          <a
            href="https://github.com/isilayc/omicsroute"
            target="_blank"
            rel="noreferrer"
          >
            Documentation
          </a>
          <a
            className="nav-feedback"
            href={FEEDBACK_URL}
            target="_blank"
            rel="noreferrer"
          >
            Send feedback
          </a>
        </nav>
      </header>

      <div className="beta-banner">
        <strong>Public beta</strong>
        <span>
          Workflow planning only — OmicsRoute does not upload your
          sequencing files. Review the final tool documentation before
          running an analysis.
        </span>
      </div>

      <section className="hero">
        <div>
          <div className="eyebrow">
            OMICSROUTE · EVIDENCE-AWARE WORKFLOW PLANNING
          </div>
          <h1>Plan a defensible bioinformatics workflow for the data you have.</h1>
          <p>
            Describe your sample and sequencing context, choose a biological
            goal, and receive an inspectable workflow plan with tool options,
            dependencies, dataset constraints, compute feasibility, evidence
            and recovery paths.
          </p>

          <div className="hero-actions">
            <button
              className="hero-primary"
              type="button"
              onClick={() =>
                plannerRef.current?.scrollIntoView({
                  behavior: "smooth",
                  block: "start",
                })
              }
            >
              Start planning
            </button>
            <a className="hero-secondary" href="#how-it-works">
              See how it works
            </a>
          </div>

          <div className="hero-chips">
            <span>Scientific fit</span>
            <span>Constraint-aware</span>
            <span>Dependency-validated</span>
            <span>Fallback-aware</span>
            <span>Exportable</span>
          </div>
        </div>

        <div className="hero-side">
          <div className={cx("api-badge", `api-${apiState}`)}>
            <span className="dot" />
            {apiState === "online"
              ? "API connected"
              : apiState === "offline"
              ? "API unavailable"
              : "Checking API"}
          </div>

          <a
            className="source-link"
            href="https://github.com/isilayc/omicsroute"
            target="_blank"
            rel="noreferrer"
          >
            View source on GitHub ↗
          </a>
        </div>
      </section>

      <section className="quick-steps" id="how-it-works">
        {[
          ["01", "Describe the analysis", "Data, organism, reference and goal."],
          ["02", "Choose the route", "Compare curated workflow strategies."],
          ["03", "Check suitability", "Constraints, dependencies and compute fit."],
          ["04", "Review & export", "Inspect evidence and download the route."],
        ].map(([number, title, copy]) => (
          <div className="quick-step" key={number}>
            <span>{number}</span>
            <strong>{title}</strong>
            <p>{copy}</p>
          </div>
        ))}
      </section>

      <details className="secondary-tools">
        <summary>About, methodology & catalogue coverage</summary>
        <div className="top-tools">
          <CoveragePanel
            coverage={coverage}
            loading={coverageLoading}
            onAudit={runCoverageAudit}
          />
          <AboutPanel />
        </div>
      </details>

      <section className="workspace" id="planner" ref={plannerRef}>
        <section className="planner-column">
          <div className="card planner-card">
            <div className="planner-toolbar">
              <div>
                <span className="planner-kicker">Analysis planner</span>
                <strong>{progressCount}/4 stages complete</strong>
              </div>

              <button
                className="reset-button"
                type="button"
                onClick={resetPlanner}
                disabled={!sampleType && !workflow}
              >
                Reset analysis
              </button>
            </div>

            <div
              className="planner-progress"
              aria-label={`${progressCount} of 4 planner stages complete`}
            >
              <span style={{ width: `${progressPercent}%` }} />
            </div>

            <div className="section-head">
              <div>
                <span className="section-number">01</span>
                <h2>Describe your analysis</h2>
              </div>
              <p>
                Start with the biological material and the data object you
                currently have.
              </p>
            </div>

            <div className="form-grid">
              <SelectField
                label="Sample type"
                value={sampleType}
                onChange={setSampleType}
                options={sampleTypes}
                disabled={apiState !== "online"}
              />

              <SelectField
                label="What data do you currently have?"
                value={dataState}
                onChange={setDataState}
                options={dataStates.map((item) => ({
                  value: item.id,
                  label: item.label,
                }))}
                disabled={!sampleType}
              />

              {isRawReads ? (
                <>
                  <SelectField
                    label="Sequencing technology"
                    value={sequencing}
                    onChange={setSequencing}
                    options={sequencingOptions}
                    disabled={!dataState}
                  />

                  <SelectField
                    label="Read type"
                    value={readType}
                    onChange={setReadType}
                    options={readTypes}
                    disabled={!sequencing}
                  />
                </>
              ) : null}
            </div>

            <ReferenceFinder
              sampleType={sampleType}
              dataState={dataState}
              supported={referenceSupported}
              referenceContext={referenceContext}
              setReferenceContext={setReferenceContext}
            />

            <div className="prebuild-compute">
              <ComputePanel
                computeProfile={computeProfile}
                setComputeProfile={setComputeProfile}
              />
            </div>

            <div className="planning-note">
              <span>🔒</span>
              <p>
                OmicsRoute plans workflows from the context you enter here.
                Your FASTQ, FASTA, BAM and count-table files are not uploaded
                to this website.
              </p>
            </div>

            <div className="section-divider" />

            <div className="section-head compact">
              <div>
                <span className="section-number">02</span>
                <h2>Choose a biological goal</h2>
              </div>
            </div>

            <div className="goal-list">
              {goals.length === 0 ? (
                <div className="empty-state">
                  Complete the analysis context above to see compatible
                  goals.
                </div>
              ) : (
                goals.map((item) => (
                  <button
                    key={item.id}
                    className={cx(
                      "goal-row",
                      goal === item.id && "selected"
                    )}
                    type="button"
                    onClick={() => setGoal(item.id)}
                  >
                    <div>
                      <strong>{item.label}</strong>
                      {item.note ? <p>{item.note}</p> : null}
                    </div>
                    <StatusPill status={item.status} />
                  </button>
                ))
              )}
            </div>

            {goal ? (
              <>
                <div className="section-divider" />

                <div className="section-head compact">
                  <div>
                    <span className="section-number">03</span>
                    <h2>Choose the analysis route</h2>
                  </div>
                </div>

                {!currentGoal?.selectable ? (
                  <div className="notice info">
                    {currentGoal?.note ||
                      "Additional input is required before this route can be built."}
                  </div>
                ) : (
                  <div className="strategy-list">
                    {strategies.map((item) => (
                      <button
                        key={item.id}
                        className={cx(
                          "strategy-row",
                          strategyId === item.id && "selected"
                        )}
                        type="button"
                        onClick={() => setStrategyId(item.id)}
                      >
                        <strong>{item.name}</strong>
                        {item.description ? <p>{item.description}</p> : null}
                      </button>
                    ))}
                  </div>
                )}

                {strategyId ? (
                  <button
                    className="build-button"
                    type="button"
                    onClick={handleBuild}
                    disabled={workflowBusy}
                  >
                    {workflowBusy
                      ? "Building workflow..."
                      : "Build workflow plan"}
                  </button>
                ) : null}
              </>
            ) : null}
          </div>

          {inspection ? (
            <div className="card control-card">
              <div className="section-head compact">
                <div>
                  <span className="section-number">Suitability</span>
                  <h2>Dataset suitability & reference guidance</h2>
                </div>
              </div>

              <DatasetSuitabilityPanel
                inspection={inspection}
                datasetProfile={datasetProfile}
                setDatasetProfile={setDatasetProfile}
                onEvaluate={() =>
                  refreshInspection({
                    dataset_profile: datasetProfile,
                  })
                }
                busy={workflowBusy}
              />

              <ReferenceGuidancePanel
                referenceData={inspection.reference_guidance}
                onScopeChange={handleScopeChange}
              />
            </div>
          ) : null}
        </section>

        <aside
          className="result-column"
          id="workflow-result"
          ref={resultRef}
        >
          <div className="card result-card">
            <div className="section-head compact">
              <div>
                <span className="section-number">04</span>
                <h2>Workflow result</h2>
              </div>
            </div>

            {!workflow ? (
              <div className="result-empty">
                <div className="result-icon">⌁</div>
                <h3>Your workflow will appear here</h3>
                <p>
                  Build a route to inspect its tools, scores, constraints,
                  technical path, evidence and recovery guidance.
                </p>
              </div>
            ) : (
              <div className="workflow">
                <span className="route-label">Selected workflow route</span>
                <h3>{workflow.name}</h3>
                {workflow.description ? <p>{workflow.description}</p> : null}

                <div className="overview-metrics">
                  <Metric label="Steps" value={overview.steps || 0} />
                  <Metric
                    label="Tool options"
                    value={overview.tool_options || 0}
                  />
                  <Metric
                    label="Required inputs"
                    value={overview.required_inputs || 0}
                  />
                </div>

                {workflow.context ? (
                  <div className="context-line">
                    {[
                      workflow.context.sample_type,
                      workflow.context.sequencing,
                      workflow.context.read_type,
                      workflow.context.goal,
                    ]
                      .filter(Boolean)
                      .join(" → ")}
                  </div>
                ) : null}

                {inspection.required_inputs?.length ? (
                  <details className="required-inputs">
                    <summary>📥 Required user inputs</summary>
                    <div>
                      {inspection.required_inputs.map((item) => (
                        <span key={item.id}>
                          {item.is_collection ? "🧺 " : ""}
                          {item.label}
                          {item.is_collection ? " — sample collection" : ""}
                        </span>
                      ))}
                    </div>
                  </details>
                ) : null}

                <DependencyPanel dependency={inspection.dependency} />

                <WorkflowLiteraturePanel research={workflowResearch} />

                <DecisionPointsPanel points={workflow.decision_points} />

                <div className="workflow-steps">
                  {(workflow.steps || []).map((step, stepIndex) => (
                    <article
                      className="workflow-step"
                      key={`${step.operation}-${stepIndex}`}
                    >
                      <div className="step-number">
                        {String(stepIndex + 1).padStart(2, "0")}
                      </div>

                      <div className="step-content">
                        <div className="step-head">
                          <div>
                            <h4>{step.name || step.operation}</h4>
                            {step.description ? <p>{step.description}</p> : null}
                          </div>
                          <span className="mode-badge">
                            {step.mode === "parallel"
                              ? "Run in parallel"
                              : "Ranked alternatives"}
                          </span>
                        </div>

                        {step.mode === "parallel" ? (
                          <div className="notice info">
                            Run multiple tools here — do not choose only one.
                            These independent branches are intentionally not
                            ranked against one another.
                          </div>
                        ) : null}

                        <div className="tool-stack">
                          {(step.tools || []).map((tool, toolIndex) => {
                            const key = `${stepIndex}:${tool.id}`;

                            return (
                              <ToolCard
                                key={key}
                                tool={tool}
                                operation={step.operation}
                                stepMode={step.mode}
                                evidence={evidenceByKey[key]}
                                biotools={biotoolsByKey[key]}
                                onEvidence={() =>
                                  loadEvidence(
                                    key,
                                    tool,
                                    step.operation
                                  )
                                }
                                onBioTools={() =>
                                  loadBioTools(key, tool)
                                }
                              />
                            );
                          })}
                        </div>

                        <RecoveryPanel recovery={step.recovery} />

                        <DiscoveryPanel
                          step={step}
                          index={stepIndex}
                          result={discoveryByStep[stepIndex]}
                          onResearch={researchStep}
                        />
                      </div>
                    </article>
                  ))}
                </div>

                <section className="export-section">
                  <div>
                    <span className="section-number">Review & export</span>
                    <h3>Save the current recommendation</h3>
                    <p>
                      Export the route for methods notes, sharing or later
                      reuse.
                    </p>
                  </div>

                  <div className="export-actions">
                    <button
                      type="button"
                      onClick={() => {
                        const item = inspection.exports?.markdown;
                        if (item) {
                          downloadText(
                            item.filename,
                            item.content,
                            item.mime
                          );
                        }
                      }}
                    >
                      Download Markdown
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        const item = inspection.exports?.json;
                        if (item) {
                          downloadText(
                            item.filename,
                            item.content,
                            item.mime
                          );
                        }
                      }}
                    >
                      Download JSON
                    </button>
                  </div>

                  <small>
                    Dataset-specific suitability decisions should be
                    interpreted together with the checks and tool
                    documentation shown above.
                  </small>
                </section>
              </div>
            )}
          </div>
        </aside>
      </section>

      {globalError ? (
        <div className="global-error">
          <strong>OmicsRoute:</strong> {globalError}
        </div>
      ) : null}

      <a
        className="floating-feedback"
        href={FEEDBACK_URL}
        target="_blank"
        rel="noreferrer"
        aria-label="Send OmicsRoute beta feedback"
      >
        Feedback
      </a>

      <footer>
        <span>OmicsRoute · Public beta</span>
        <span>
          Evidence-aware research decision support · verify final parameters
          against current tool documentation
        </span>
      </footer>
    </main>
  );
}
