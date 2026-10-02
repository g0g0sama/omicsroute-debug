const API_BASE =
  process.env.NEXT_PUBLIC_OMICSROUTE_API_URL ||
  "http://127.0.0.1:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    const message =
      body?.detail ||
      body?.error ||
      `Request failed with HTTP ${response.status}`;

    throw new Error(
      typeof message === "string"
        ? message
        : JSON.stringify(message)
    );
  }

  return body;
}

export const getHealth = () => request("/health");
export const getSampleTypes = () => request("/v1/sample-types");

export const getDataStates = (sampleType) =>
  request(`/v1/data-states?sample_type=${encodeURIComponent(sampleType)}`);

export const getSequencingOptions = (sampleType) =>
  request(
    `/v1/sequencing-options?sample_type=${encodeURIComponent(sampleType)}`
  );

export const getReadTypes = (sampleType, sequencing) =>
  request(
    `/v1/read-types?sample_type=${encodeURIComponent(
      sampleType
    )}&sequencing=${encodeURIComponent(sequencing)}`
  );

export const getGoals = (payload) =>
  request("/v1/goals", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getStrategies = (payload) =>
  request("/v1/strategies", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const inspectWorkflow = (payload) =>
  request("/v1/workflow/inspect", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const researchWorkflow = (payload) =>
  request("/v1/workflow-research", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const searchTaxa = (query) =>
  request(`/v1/reference/taxa?q=${encodeURIComponent(query)}`);

export const searchAssemblies = (taxId) =>
  request(
    `/v1/reference/assemblies?tax_id=${encodeURIComponent(taxId)}`
  );

export const getReferenceContext = (accession) =>
  request(
    `/v1/reference/context/${encodeURIComponent(accession)}`
  );

export const getReferenceGuidance = (goal, workflowId, scopeId) => {
  const params = new URLSearchParams({
    goal,
    workflow_id: workflowId,
  });

  if (scopeId) params.set("scope_id", scopeId);

  return request(`/v1/reference-guidance?${params.toString()}`);
};

export const getToolEvidence = (toolName, operation) =>
  request("/v1/tool-evidence", {
    method: "POST",
    body: JSON.stringify({
      tool_name: toolName,
      operation,
    }),
  });

export const getBioTools = (toolName) =>
  request(`/v1/biotools?tool_name=${encodeURIComponent(toolName)}`);

export const researchAlternatives = (payload) =>
  request("/v1/discovery", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getCoverage = (fullAudit = false) =>
  request(
    `/v1/catalog/coverage?validate_dependencies=${
      fullAudit ? "true" : "false"
    }`
  );
