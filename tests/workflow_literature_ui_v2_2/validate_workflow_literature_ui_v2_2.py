from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

api_js = (ROOT / "frontend" / "lib" / "api.js").read_text(encoding="utf-8")
page_js = (ROOT / "frontend" / "app" / "page.js").read_text(encoding="utf-8")
css = (ROOT / "frontend" / "app" / "globals.css").read_text(encoding="utf-8")

checks = {
    "API client endpoint": 'request("/v1/workflow-research"' in api_js,
    "researchWorkflow import": "researchWorkflow," in page_js,
    "workflowResearch state": "const [workflowResearch, setWorkflowResearch]" in page_js,
    "non-blocking workflow research": "void loadWorkflowResearch();" in page_js,
    "literature panel component": "function WorkflowLiteraturePanel" in page_js,
    "literature panel render": "<WorkflowLiteraturePanel research={workflowResearch} />" in page_js,
    "contextual candidate language": "Literature signals not currently in route" in page_js,
    "ordering caveat": "does not infer executable step order" in " ".join(page_js.split()),
    "UI CSS": ".workflow-literature" in css,
}

failed = [name for name, ok in checks.items() if not ok]

print("=" * 78)
print("OmicsRoute workflow literature UI v2.2")
print("=" * 78)

for name, ok in checks.items():
    print(f"{name}: {'PASS' if ok else 'FAIL'}")

if failed:
    print("")
    print("RESULT: FAIL")
    raise SystemExit("Missing/failed checks: " + ", ".join(failed))

print("")
print("RESULT: PASS")
