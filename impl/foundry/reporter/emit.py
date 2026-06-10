"""SARIF 2.1.0 + Markdown emitters."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_sarif(findings: list[dict[str, Any]], out: Path) -> None:
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for f in findings:
        rid = f["rule_id"] or f["vuln_class"]
        rules.setdefault(
            rid,
            {
                "id": rid,
                "name": rid,
                "shortDescription": {"text": f["vuln_class"]},
                "defaultConfiguration": {"level": _level(f.get("severity"))},
            },
        )
        result = {
            "ruleId": rid,
            "level": _level(f.get("severity")),
            "message": {"text": (f.get("triager_notes") or f.get("detector_rationale") or "")[:1000]},
            "locations": [
                {
                    "logicalLocations": [{"name": f["symbol"]}],
                    "physicalLocation": {
                        "artifactLocation": {"uri": f["path"]},
                    },
                }
            ],
            "fingerprints": {"foundry/v1": f["fingerprint"]},
            "properties": {
                "exploited": bool(f.get("exploited")),
                "verdict": f.get("verdict"),
                "vulnClass": f["vuln_class"],
                "citations": [
                    {"path": c["cite_path"], "symbol": c["cite_symbol"]}
                    for c in f.get("_citations", [])
                ],
            },
        }
        results.append(result)

    sarif = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "FoundrySec",
                        "version": "0.1.0",
                        "informationUri": "https://github.com/CiscoDevNet/foundry-security-spec",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    out.write_text(json.dumps(sarif, indent=2))


def write_markdown(findings: list[dict[str, Any]], out: Path) -> None:
    lines = ["# Foundry Sec — Evaluation Report\n"]
    if not findings:
        lines.append("_No findings survived the evidence gate._\n")
        out.write_text("\n".join(lines))
        return

    by_severity = sorted(findings, key=lambda f: _sev_rank(f.get("severity")))
    lines.append(f"**Findings:** {len(findings)}\n")
    lines.append(f"**Exploited:** {sum(1 for f in findings if f.get('exploited'))}\n\n")

    for f in by_severity:
        lines.append(f"## {f['vuln_class']} — `{f['symbol']}`")
        lines.append("")
        lines.append(f"- **Path:** `{f['path']}`")
        lines.append(f"- **Rule:** `{f['rule_id'] or '(none)'}`")
        lines.append(f"- **Verdict:** {f['verdict']}")
        lines.append(f"- **Severity:** {f.get('severity') or 'unspecified'}")
        lines.append(f"- **Exploited:** {'✅' if f.get('exploited') else '—'}")
        lines.append(f"- **Fingerprint:** `{f['fingerprint']}`")
        lines.append("")
        lines.append(f"### Triager notes\n\n{f.get('triager_notes') or '_(none)_'}\n")
        cites = f.get("_citations", [])
        if cites:
            lines.append("### Evidence citations\n")
            for c in cites:
                lines.append(f"- `{c['cite_path']}::{c['cite_symbol']}` — `{c['quoted_excerpt'][:200]}`")
            lines.append("")
    out.write_text("\n".join(lines))


def _level(sev: str | None) -> str:
    return {"critical": "error", "high": "error", "medium": "warning", "low": "note"}.get(
        (sev or "").lower(), "warning"
    )


def _sev_rank(sev: str | None) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get((sev or "").lower(), 4)
