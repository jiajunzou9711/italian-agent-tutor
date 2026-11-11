"""Deterministic reference model for the documented Adaptive Controller.

The AI tutor performs semantic evaluation. This small state machine tests the
protocol invariants after an evaluation has been classified.
"""

from dataclasses import dataclass, replace
from enum import Enum


class Outcome(str, Enum):
    INDEPENDENT = "independent"
    ASSISTED = "assisted"
    LOCAL_ERROR = "local_error"
    BLOCKING_ERROR = "blocking_error"
    FRESH_SCENE_SUCCESS = "fresh_scene_success"
    LATER_SESSION_SUCCESS = "later_session_success"
    DELAYED_CHECK_FAILURE = "delayed_check_failure"
    REPAIR_PRESENTED = "repair_presented"
    REPAIR_SUCCESS = "repair_success"
    REPAIR_FAILURE = "repair_failure"


@dataclass(frozen=True)
class ControllerState:
    level: str = "Learning"
    independent_streak: int = 0
    difficulty_down_streak: int = 0
    load: int = 0
    repairs_used: int = 0
    main_point: str = "current"
    parked: bool = False


@dataclass(frozen=True)
class Decision:
    state: ControllerState
    action: str
    evidence: str
    preserve_main_point: bool = True


def decide(state: ControllerState, outcome: Outcome) -> Decision:
    if outcome in {Outcome.INDEPENDENT, Outcome.LOCAL_ERROR}:
        streak = state.independent_streak + 1
        raised = streak >= 2
        next_state = replace(
            state,
            independent_streak=0 if raised else streak,
            difficulty_down_streak=0,
            load=state.load + (1 if raised else 0),
        )
        if outcome is Outcome.LOCAL_ERROR:
            action = "correct_and_raise_one_variable" if raised else "correct_and_delayed_check"
        else:
            action = "raise_one_variable" if raised else "continue"
        return Decision(next_state, action, "E2")

    if outcome in {Outcome.ASSISTED, Outcome.BLOCKING_ERROR}:
        down_streak = state.difficulty_down_streak + 1
        lower = outcome is Outcome.BLOCKING_ERROR or down_streak >= 2
        next_state = replace(
            state,
            independent_streak=0,
            difficulty_down_streak=0 if lower else down_streak,
            load=state.load - (1 if lower else 0),
        )
        action = "lower_one_variable" if lower else "hold"
        return Decision(next_state, action, "E1")

    if outcome is Outcome.REPAIR_PRESENTED:
        return Decision(state, "await_repair_answer", "E0")

    if outcome in {Outcome.REPAIR_SUCCESS, Outcome.REPAIR_FAILURE}:
        repairs = state.repairs_used + 1
        parked = repairs > 2
        next_state = replace(
            state,
            repairs_used=min(repairs, 2),
            parked=parked,
            independent_streak=0,
        )
        if parked:
            return Decision(next_state, "park_point", "E1")
        evidence = "E2" if outcome is Outcome.REPAIR_SUCCESS else "E1"
        return Decision(next_state, "continue_after_repair", evidence)

    if outcome is Outcome.FRESH_SCENE_SUCCESS:
        return Decision(replace(state, level="Pending", independent_streak=0), "park_pending", "E3")

    if outcome is Outcome.LATER_SESSION_SUCCESS:
        return Decision(replace(state, level="Sealed", independent_streak=0), "space_review", "E4")

    if outcome is Outcome.DELAYED_CHECK_FAILURE:
        # An unprompted failure moves the point down exactly one level.
        lower_level = {"Sealed": "Pending", "Pending": "Learning"}.get(state.level, state.level)
        return Decision(
            replace(state, level=lower_level, independent_streak=0, load=state.load - 1),
            "move_down_one_level",
            "E0",
        )

    raise ValueError(f"Unsupported outcome: {outcome}")
