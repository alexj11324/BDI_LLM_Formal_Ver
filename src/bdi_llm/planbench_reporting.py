"""Reporting helpers for PlanBench paper tables."""

from __future__ import annotations

from typing import Any


DOMAIN_ORDER = [
    "blocksworld",
    "logistics",
    "depots",
    "obfuscated_deceptive_logistics",
    "obfuscated_randomized_logistics",
]

DOMAIN_LABELS = {
    "blocksworld": "Blocksworld",
    "logistics": "Logistics",
    "depots": "Depots",
    "obfuscated_deceptive_logistics": "Obf.\\ Deceptive",
    "obfuscated_randomized_logistics": "Obf.\\ Randomized",
}


def _percentage(rate: float) -> str:
    return f"{rate * 100:.1f}\\%"


def _appendix_cell(success_count: int, rate: float) -> str:
    return f"{success_count} ({_percentage(rate)})"


def aggregate_planbench_results(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-domain result payloads into paper-ready statistics."""
    domains: list[dict[str, Any]] = []
    total_n = 0
    total_stage_counts = {
        "baseline": 0,
        "bdi": 0,
        "bdi_repair": 0,
    }

    for domain in DOMAIN_ORDER:
        payload = payloads[domain]
        total_instances = int(payload["total_instances"])
        summary = payload["summary"]
        record = {
            "key": domain,
            "label": DOMAIN_LABELS[domain],
            "n": total_instances,
            "baseline": {
                "success_count": int(summary["baseline"]["success_count"]),
                "success_rate": float(summary["baseline"]["success_rate"]),
            },
            "bdi": {
                "success_count": int(summary["bdi"]["success_count"]),
                "success_rate": float(summary["bdi"]["success_rate"]),
            },
            "bdi_repair": {
                "success_count": int(summary["bdi_repair"]["success_count"]),
                "success_rate": float(summary["bdi_repair"]["success_rate"]),
            },
        }
        domains.append(record)
        total_n += total_instances
        total_stage_counts["baseline"] += record["baseline"]["success_count"]
        total_stage_counts["bdi"] += record["bdi"]["success_count"]
        total_stage_counts["bdi_repair"] += record["bdi_repair"]["success_count"]

    return {
        "domains": domains,
        "total": {
            "label": "All",
            "n": total_n,
            "baseline": {
                "success_count": total_stage_counts["baseline"],
                "success_rate": total_stage_counts["baseline"] / total_n if total_n > 0 else 0.0,
            },
            "bdi": {
                "success_count": total_stage_counts["bdi"],
                "success_rate": total_stage_counts["bdi"] / total_n if total_n > 0 else 0.0,
            },
            "bdi_repair": {
                "success_count": total_stage_counts["bdi_repair"],
                "success_rate": (
                    total_stage_counts["bdi_repair"] / total_n if total_n > 0 else 0.0
                ),
            },
        },
    }


def render_latex_tables(aggregate: dict[str, Any]) -> dict[str, str]:
    """Render main and appendix LaTeX tables from aggregate statistics."""
    main_lines = [
        "Domain & $N$ & Baseline & BDI & BDI-Repair \\\\",
        "\\midrule",
    ]
    appendix_lines = [
        "Domain & $N$ & Baseline & BDI & BDI-Rep. \\\\",
        "\\midrule",
    ]

    for record in aggregate["domains"]:
        main_lines.append(
            (
                f"{record['label']} & {record['n']} & "
                f"{_percentage(record['baseline']['success_rate'])} & "
                f"{_percentage(record['bdi']['success_rate'])} & "
                f"\\textbf{{{_percentage(record['bdi_repair']['success_rate'])}}} \\\\"
            )
        )
        appendix_lines.append(
            (
                f"{record['label']} & {record['n']} & "
                f"{_appendix_cell(record['baseline']['success_count'], record['baseline']['success_rate'])} & "
                f"{_appendix_cell(record['bdi']['success_count'], record['bdi']['success_rate'])} & "
                f"\\textbf{{{_appendix_cell(record['bdi_repair']['success_count'], record['bdi_repair']['success_rate'])}}} \\\\"
            )
        )

    total = aggregate["total"]
    main_lines.extend(
        [
            "\\midrule",
            (
                f"\\textbf{{{total['label']}}} & \\textbf{{{total['n']}}} & "
                f"\\textbf{{{_percentage(total['baseline']['success_rate'])}}} & "
                f"\\textbf{{{_percentage(total['bdi']['success_rate'])}}} & "
                f"\\textbf{{{_percentage(total['bdi_repair']['success_rate'])}}} \\\\"
            ),
        ]
    )
    appendix_lines.extend(
        [
            "\\midrule",
            (
                f"\\textbf{{Total}} & \\textbf{{{total['n']}}} & "
                f"\\textbf{{{_appendix_cell(total['baseline']['success_count'], total['baseline']['success_rate'])}}} & "
                f"\\textbf{{{_appendix_cell(total['bdi']['success_count'], total['bdi']['success_rate'])}}} & "
                f"\\textbf{{{_appendix_cell(total['bdi_repair']['success_count'], total['bdi_repair']['success_rate'])}}} \\\\"
            ),
        ]
    )

    return {
        "main": "\n".join(main_lines) + "\n",
        "appendix": "\n".join(appendix_lines) + "\n",
    }
