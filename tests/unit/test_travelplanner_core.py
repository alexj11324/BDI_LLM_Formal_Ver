from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bdi_llm.travelplanner.adapter import TravelPlannerTaskAdapter
from src.bdi_llm.travelplanner.official import summarize_travelplanner_results
from src.bdi_llm.travelplanner.schemas import TravelDayPlan, TravelPlannerItinerary
from src.bdi_llm.travelplanner.serializer import TravelPlannerPlanSerializer


SAMPLE = {
    'idx': 1,
    'split': 'validation',
    'query': 'Plan a 3-day trip from Washington to Myrtle Beach under $1400.',
    'reference_information': [{'Description': 'Flights', 'Content': '...'}],
    'days': 3,
    'level': 'easy',
    'org': 'Washington',
    'dest': 'Myrtle Beach',
    'date': ['2022-03-13', '2022-03-14', '2022-03-15'],
}


def test_task_adapter_builds_planning_task():
    task = TravelPlannerTaskAdapter().to_planning_task(SAMPLE)
    assert task.task_id == '1'
    assert task.domain_name == 'travelplanner'
    assert 'Washington' in task.beliefs
    assert task.metadata['days'] == 3


def test_serializer_pads_days_and_builds_submission():
    itinerary = TravelPlannerItinerary(
        summary='trip',
        plan=[
            TravelDayPlan(day=1, current_city='from Washington to Myrtle Beach', transportation='Flight', breakfast='-', attraction='SkyWheel Myrtle Beach, Myrtle Beach', lunch='Cafe, Myrtle Beach', dinner='Bistro, Myrtle Beach', accommodation='Hotel, Myrtle Beach'),
            TravelDayPlan(day=2, current_city='Myrtle Beach', transportation='-', breakfast='Cafe, Myrtle Beach', attraction='Boardwalk, Myrtle Beach', lunch='Cafe2, Myrtle Beach', dinner='Bistro2, Myrtle Beach', accommodation='Hotel, Myrtle Beach'),
        ],
    )
    task = TravelPlannerTaskAdapter().to_planning_task(SAMPLE)
    serializer = TravelPlannerPlanSerializer()
    submission = serializer.to_submission_record(itinerary, task)
    assert submission['idx'] == 1
    assert len(submission['plan']) == 3
    assert submission['plan'][2]['current_city'].startswith("You don't need")


def test_summary_aggregation_uses_final_pass():
    summary = summarize_travelplanner_results([
        {'metrics': {'delivery': True, 'commonsense_pass': True, 'hard_constraint_pass': True, 'final_pass': True}},
        {'metrics': {'delivery': True, 'commonsense_pass': False, 'hard_constraint_pass': False, 'final_pass': False}},
    ])
    assert summary['success_count'] == 1
    assert summary['failed_count'] == 1
    assert summary['final_pass_rate'] == 0.5
