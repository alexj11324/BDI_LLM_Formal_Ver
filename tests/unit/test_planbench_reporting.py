"""Tests for PlanBench paper table aggregation."""

from __future__ import annotations

from src.bdi_llm.planbench_reporting import aggregate_planbench_results, render_latex_tables


def test_aggregate_planbench_results_and_render_tables():
    aggregate = aggregate_planbench_results(
        {
            "blocksworld": {
                "total_instances": 1103,
                "summary": {
                    "baseline": {"success_count": 1103, "success_rate": 1.0},
                    "bdi": {"success_count": 1103, "success_rate": 1.0},
                    "bdi_repair": {"success_count": 1103, "success_rate": 1.0},
                },
            },
            "logistics": {
                "total_instances": 572,
                "summary": {
                    "baseline": {"success_count": 0, "success_rate": 0.0},
                    "bdi": {"success_count": 557, "success_rate": 557 / 572},
                    "bdi_repair": {"success_count": 572, "success_rate": 1.0},
                },
            },
            "depots": {
                "total_instances": 501,
                "summary": {
                    "baseline": {"success_count": 498, "success_rate": 498 / 501},
                    "bdi": {"success_count": 478, "success_rate": 478 / 501},
                    "bdi_repair": {"success_count": 501, "success_rate": 1.0},
                },
            },
            "obfuscated_deceptive_logistics": {
                "total_instances": 572,
                "summary": {
                    "baseline": {"success_count": 546, "success_rate": 546 / 572},
                    "bdi": {"success_count": 546, "success_rate": 546 / 572},
                    "bdi_repair": {"success_count": 572, "success_rate": 1.0},
                },
            },
            "obfuscated_randomized_logistics": {
                "total_instances": 572,
                "summary": {
                    "baseline": {"success_count": 547, "success_rate": 547 / 572},
                    "bdi": {"success_count": 536, "success_rate": 536 / 572},
                    "bdi_repair": {"success_count": 572, "success_rate": 1.0},
                },
            },
        }
    )

    assert aggregate["total"]["n"] == 3320
    assert aggregate["total"]["baseline"]["success_count"] == 2694
    assert aggregate["total"]["bdi"]["success_count"] == 3220
    assert aggregate["total"]["bdi_repair"]["success_count"] == 3320

    tables = render_latex_tables(aggregate)
    assert "Domain & $N$ & Baseline & BDI & BDI-Repair" in tables["main"]
    assert "Logistics & 572 & 0.0\\% & 97.4\\% & \\textbf{100.0\\%}" in tables["main"]
    assert "Domain & $N$ & Baseline & BDI & BDI-Rep." in tables["appendix"]
    assert "Logistics & 572 & 0 (0.0\\%) & 557 (97.4\\%) & \\textbf{572 (100.0\\%)}" in tables["appendix"]
