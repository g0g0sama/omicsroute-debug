"""Verify the unchanged browser UI against a configured backend."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def run(base_url: str, output: Path, chromium: str | None = None):
    output.mkdir(parents=True, exist_ok=True)
    results = []
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            **({"executable_path": chromium} if chromium else {})
        )
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_default_timeout(120_000)
        for sequencing, read_type, goal in (
            ("Illumina", "Paired-end", "Functional profiling"),
            ("Oxford Nanopore", "Long reads", "Taxonomic profiling"),
        ):
            page.goto(base_url, wait_until="domcontentloaded")
            expect(page.get_by_text("API connected", exact=True)).to_be_visible()
            for label, value in (
                ("Sample type", "Metagenome"),
                ("What data do you currently have?", "raw_reads"),
                ("Sequencing technology", sequencing),
                ("Read type", read_type),
            ):
                page.locator("label.field").filter(
                    has=page.get_by_text(label, exact=True)
                ).locator("select").select_option(value)
            page.locator(".goal-row").filter(has=page.get_by_text(goal, exact=True)).click()
            page.locator(".strategy-row").first.click()
            with page.expect_response(lambda response: "/v1/workflow/inspect" in response.url) as pending:
                page.get_by_role("button", name="Build workflow plan", exact=True).click()
            response = pending.value
            if response.status != 200:
                raise AssertionError(f"Inspection failed: {response.status} {response.text()}")
            inspection = response.json()
            if not inspection["workflow"].get("steps"):
                raise AssertionError("Built workflow contains no steps")
            downloads = []
            for label, kind in (("Download Markdown", "markdown"), ("Download JSON", "json")):
                with page.expect_download() as pending_download:
                    page.get_by_role("button", name=label, exact=True).click()
                download = pending_download.value
                target = output / f"{sequencing.replace(' ', '-')}-{download.suggested_filename}"
                download.save_as(target)
                content = target.read_text(encoding="utf-8")
                if content != inspection["exports"][kind]["content"]:
                    raise AssertionError(f"{label} differs from the API export")
                if kind == "json":
                    json.loads(content)
                downloads.append(str(target))
            page.screenshot(path=str(output / f"{sequencing.replace(' ', '-')}.png"), full_page=True)
            results.append({"sequencing": sequencing, "read_type": read_type, "goal": goal, "workflow": inspection["workflow"].get("id"), "downloads": downloads})
            print(f"PASS: {sequencing}, workflow and both exports", flush=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        if errors:
            raise AssertionError(f"Browser errors: {errors}")
        (output / "results.json").write_text(json.dumps({"base_url": base_url, "scenarios": results, "page_errors": errors}, indent=2) + "\n")
        browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chromium", help="Optional path to an existing Chromium executable")
    args = parser.parse_args()
    run(args.base_url, args.output, args.chromium)


if __name__ == "__main__":
    main()
