from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from typing import Any

import dspy

from ..planning_task import PlanningTask
from ..planner.dspy_config import configure_dspy
from .review import (
    apply_patch,
    assess_patch_scope,
    build_non_oracle_diagnostics,
    critique_itinerary,
)
from .schemas import TravelPlanCritique, TravelPlannerItinerary
from .signatures import (
    GenerateTravelPlanBaseline,
    GenerateTravelPlanBDI,
    GenerateTravelPlanBDILegacy,
    GenerateTravelPlanBDIv3,
    GenerateTravelPlanChecklistV4,
    RenderTravelPlanFromChecklistV4,
    CritiqueTravelPlan,
    RepairTravelPlan,
    RepairTravelPlanPatch,
)


@dataclass
class TravelPlannerGenerationResult:
    itinerary: TravelPlannerItinerary
    raw: Any


@dataclass
class TravelPlannerRefinementResult:
    initial_itinerary: TravelPlannerItinerary
    final_itinerary: TravelPlannerItinerary
    diagnostics: dict[str, Any]
    raw_repairs: list[Any] = field(default_factory=list)


class TravelPlannerGenerator:
    def __init__(self):
        configure_dspy()
        self._baseline = dspy.Predict(GenerateTravelPlanBaseline)
        self._bdi_legacy = dspy.ChainOfThought(GenerateTravelPlanBDILegacy)
        self._bdi = dspy.ChainOfThought(GenerateTravelPlanBDI)
        self._bdi_v3 = dspy.ChainOfThought(GenerateTravelPlanBDIv3)
        self._bdi_v4_checklist = dspy.ChainOfThought(GenerateTravelPlanChecklistV4)
        self._bdi_v4_render = dspy.ChainOfThought(RenderTravelPlanFromChecklistV4)
        self._critique = dspy.ChainOfThought(CritiqueTravelPlan)
        self._repair = dspy.ChainOfThought(RepairTravelPlan)
        self._patch_repair = dspy.ChainOfThought(RepairTravelPlanPatch)
        self.prompt_version = os.environ.get('TRAVELPLANNER_BDI_PROMPT_VERSION', 'v3').strip().lower()

    def generate_baseline(self, beliefs: str, desire: str, domain_context: str) -> TravelPlannerGenerationResult:
        pred = self._baseline(beliefs=beliefs, desire=desire, domain_context=domain_context or '')
        return TravelPlannerGenerationResult(itinerary=pred.itinerary, raw=pred)

    def generate_bdi(self, beliefs: str, desire: str, domain_context: str) -> TravelPlannerGenerationResult:
        if self.prompt_version == 'legacy':
            program = self._bdi_legacy
        elif self.prompt_version == 'v3':
            program = self._bdi_v3
        elif self.prompt_version == 'v4':
            checklist_pred = self._bdi_v4_checklist(
                beliefs=beliefs,
                desire=desire,
                domain_context=domain_context or '',
            )
            render_pred = self._bdi_v4_render(
                beliefs=beliefs,
                desire=desire,
                domain_context=domain_context or '',
                checklist_json=json.dumps(checklist_pred.checklist.model_dump(), ensure_ascii=False, indent=2),
            )
            return TravelPlannerGenerationResult(
                itinerary=render_pred.itinerary,
                raw={
                    'checklist': checklist_pred,
                    'render': render_pred,
                    'shortlist': getattr(render_pred, 'shortlist', None),
                },
            )
        else:
            program = self._bdi
        pred = program(beliefs=beliefs, desire=desire, domain_context=domain_context or '')
        return TravelPlannerGenerationResult(itinerary=pred.itinerary, raw=pred)

    def critique(
        self,
        beliefs: str,
        desire: str,
        domain_context: str,
        itinerary: TravelPlannerItinerary,
    ) -> TravelPlanCritique:
        pred = self._critique(
            beliefs=beliefs,
            desire=desire,
            domain_context=domain_context or '',
            itinerary_json=json.dumps(itinerary.model_dump(), ensure_ascii=False, indent=2),
        )
        return pred.critique

    def repair(
        self,
        beliefs: str,
        desire: str,
        domain_context: str,
        previous_itinerary: TravelPlannerItinerary,
        evaluator_feedback: str,
    ) -> TravelPlannerGenerationResult:
        pred = self._repair(
            beliefs=beliefs,
            desire=desire,
            domain_context=domain_context or '',
            previous_itinerary_json=json.dumps(previous_itinerary.model_dump(), ensure_ascii=False, indent=2),
            evaluator_feedback=evaluator_feedback,
        )
        return TravelPlannerGenerationResult(itinerary=pred.itinerary, raw=pred)

    def repair_patch(
        self,
        task: PlanningTask,
        previous_itinerary: TravelPlannerItinerary,
        critique: TravelPlanCritique | None = None,
        oracle_feedback: str = '',
    ) -> TravelPlannerGenerationResult:
        critique = critique or TravelPlanCritique(summary='', issues=[])
        pred = self._patch_repair(
            beliefs=task.beliefs,
            desire=task.desire,
            domain_context=task.domain_context or '',
            previous_itinerary_json=json.dumps(previous_itinerary.model_dump(), ensure_ascii=False, indent=2),
            critique_json=critique.to_prompt_json(),
            oracle_feedback=oracle_feedback or '',
        )
        patched = apply_patch(previous_itinerary, pred.patch, task)
        return TravelPlannerGenerationResult(itinerary=patched, raw=pred)

    def run_non_oracle_repair(
        self,
        task: PlanningTask,
        itinerary: TravelPlannerItinerary,
        *,
        max_passes: int = 1,
    ) -> TravelPlannerRefinementResult:
        initial = itinerary.model_copy(deep=True)
        current = initial
        critiques: list[TravelPlanCritique] = []
        raw_repairs: list[Any] = []
        passes_used = 0
        guardrails: list[dict[str, Any]] = []
        previous_assessment = None
        previous_codes: tuple[str, ...] | None = None

        for _ in range(max_passes):
            critique = critique_itinerary(current, task)
            if not critique.should_repair:
                break
            current_codes = tuple(sorted(issue.code for issue in critique.blocking_issues))
            if previous_codes is not None and current_codes == previous_codes:
                guardrails.append({
                    'accepted': False,
                    'reason': 'same critique codes repeated after a patch',
                    'issue_codes': list(current_codes),
                })
                break
            critiques.append(critique)
            repaired = self.repair_patch(task, current, critique=critique)
            assessment = assess_patch_scope(
                current,
                repaired.itinerary,
                task,
                critique,
                previous_stats=previous_assessment,
            )
            post_critique = critique_itinerary(repaired.itinerary, task)
            before_blocking = len(critique.blocking_issues)
            after_blocking = len(post_critique.blocking_issues)
            guardrails.append({
                'accepted': assessment.accepted,
                'reason': assessment.reason,
                'changed_days': assessment.changed_days,
                'changed_fields': assessment.changed_fields,
                'touched_fields': assessment.touched_fields,
                'issue_codes': assessment.issue_codes,
                'before_blocking_issue_count': before_blocking,
                'after_blocking_issue_count': after_blocking,
            })
            if not assessment.accepted:
                break
            if after_blocking >= before_blocking:
                guardrails[-1]['accepted'] = False
                guardrails[-1]['reason'] = (
                    'deterministic blocking issue count did not decrease after patch'
                )
                break
            raw_repairs.append(repaired.raw)
            passes_used += 1
            if repaired.itinerary == current:
                break
            previous_assessment = assessment
            previous_codes = current_codes
            current = repaired.itinerary

        diagnostics = build_non_oracle_diagnostics(
            initial,
            current,
            task,
            critiques,
            passes_used,
            guardrails=guardrails,
        )
        return TravelPlannerRefinementResult(
            initial_itinerary=initial,
            final_itinerary=current,
            diagnostics=diagnostics,
            raw_repairs=raw_repairs,
        )

    def run_oracle_repair(
        self,
        task: PlanningTask,
        itinerary: TravelPlannerItinerary,
        oracle_feedback: str,
    ) -> TravelPlannerRefinementResult:
        initial = itinerary.model_copy(deep=True)
        oracle_feedback = (oracle_feedback or '').strip()
        if not oracle_feedback:
            return TravelPlannerRefinementResult(
                initial_itinerary=initial,
                final_itinerary=initial,
                diagnostics={
                    'triggered': False,
                    'passes_used': 0,
                    'changed_days': 0,
                    'changed_fields': 0,
                    'issue_categories': {},
                    'issues': [],
                },
                raw_repairs=[],
            )

        repaired = self.repair_patch(
            task,
            initial,
            critique=TravelPlanCritique(summary='oracle feedback follow-up', issues=[]),
            oracle_feedback=oracle_feedback,
        )
        oracle_critique = TravelPlanCritique(summary='oracle feedback follow-up', issues=[])
        assessment = assess_patch_scope(
            initial,
            repaired.itinerary,
            task,
            oracle_critique,
        )
        diagnostics = build_non_oracle_diagnostics(
            initial,
            repaired.itinerary,
            task,
            [],
            1,
            guardrails=[{
                'accepted': assessment.accepted,
                'reason': assessment.reason,
                'changed_days': assessment.changed_days,
                'changed_fields': assessment.changed_fields,
                'touched_fields': assessment.touched_fields,
                'issue_codes': assessment.issue_codes,
            }],
        )
        diagnostics['triggered'] = True
        diagnostics['issue_categories'] = {'oracle_feedback': 1}
        return TravelPlannerRefinementResult(
            initial_itinerary=initial,
            final_itinerary=repaired.itinerary,
            diagnostics=diagnostics,
            raw_repairs=[repaired.raw],
        )
