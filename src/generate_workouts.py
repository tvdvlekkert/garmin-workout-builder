"""Generates the 16 Garmin Connect strength workout JSON files (Day A/B x 8 weeks).

Writes out/week{N}-day{A|B}.json. Does not talk to the network -- see
src/garmin/cli.py for that. Run: bazel run //:generate_workouts
"""

import itertools
import json
import logging
import math
import sys
from collections import namedtuple

from dev.workspace import workspace_root

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = workspace_root()

# region exercise lookup
# (category, exerciseName) pairs from Garmin's public catalog (ref/Exercises.json,
# fetched 2026-07-15). Cross-checked against pairs read off a real workout to
# confirm catalog keys match the JSON schema's fields.
# glute_bridge maps to plain HIP_RAISE, not the more advanced (leg-extension)
# BRIDGE_WITH_LEG_EXTENSION.

ExerciseRef = namedtuple("ExerciseRef", ["category", "exercise_name"])

EX = {
    "jumping_jacks": ExerciseRef("CARDIO", "JUMPING_JACKS"),
    "bodyweight_squat": ExerciseRef("SQUAT", "SQUAT"),
    "walking_lunge": ExerciseRef("LUNGE", "LUNGE"),
    "glute_bridge": ExerciseRef("HIP_RAISE", "HIP_RAISE"),
    "plank": ExerciseRef("PLANK", "PLANK"),
    "db_jump_squat": ExerciseRef("PLYO", "DUMBBELL_JUMP_SQUAT"),
    "barbell_back_squat": ExerciseRef("SQUAT", "BARBELL_BACK_SQUAT"),
    # empty-bar squat/deadlift are still barbell back squat/deadlift
    # movements, just at bodyweight loading -- reuse the main-lift pair.
    "empty_bar_squat": ExerciseRef("SQUAT", "BARBELL_BACK_SQUAT"),
    "empty_bar_deadlift": ExerciseRef("DEADLIFT", "BARBELL_DEADLIFT"),
    "barbell_row": ExerciseRef("ROW", "BARBELL_ROW"),
    "push_up": ExerciseRef("PUSH_UP", "PUSH_UP"),
    "barbell_rdl": ExerciseRef("DEADLIFT", "ROMANIAN_DEADLIFT"),
    "barbell_deadlift": ExerciseRef("DEADLIFT", "BARBELL_DEADLIFT"),
    # No standing/broad jump exists in Garmin's catalog (confirmed absent) --
    # reuses Day A's power exercise per user decision.
    "broad_jump": ExerciseRef("PLYO", "DUMBBELL_JUMP_SQUAT"),
    "rfe_split_squat": ExerciseRef("LUNGE", "BACK_FOOT_ELEVATED_DUMBBELL_SPLIT_SQUAT"),
    # Day A's loaded unilateral lift (per coach), rotated barbell <-> dumbbell
    # session to session -- the two are interchangeable. Both started light.
    "barbell_bulgarian_split_squat": ExerciseRef("LUNGE", "BARBELL_BULGARIAN_SPLIT_SQUAT"),
    "db_bulgarian_split_squat": ExerciseRef("LUNGE", "DUMBBELL_BULGARIAN_SPLIT_SQUAT"),
    "single_arm_db_row": ExerciseRef("ROW", "SINGLE_ARM_NEUTRAL_GRIP_DUMBBELL_ROW"),
    "db_floor_press": ExerciseRef("BENCH_PRESS", "DUMBBELL_FLOOR_PRESS"),
}

# endregion

# region 8-week progression
# Training maxes the weekly %s scale off (not true 1RMs). Squat recalibrated to a
# 180 TM after week 1 (prescribed 205 was too heavy off ~4 years); deadlift is
# still the original estimate -- revisit once day B has run for real.

SQUAT_1RM = 180
DEADLIFT_1RM = 220

# Day A's unilateral lift alternates barbell <-> dumbbell Bulgarian split squat
# session to session (coach: the two are interchangeable). Both start light and
# are fixed, not tied to the main-lift progression -- bump by hand as they get
# easy. Dumbbell weight is per hand.
# (exercise_key, weight_lb)
SPLIT_SQUAT_VARIANTS = [
    ("barbell_bulgarian_split_squat", 45),
    ("db_bulgarian_split_squat", 25),
]

# Warmup timing: each move is a timed hold of WARMUP_WORK_SECONDS with
# WARMUP_REST_SECONDS between, except the moves listed in WARMUP_WORK_OVERRIDES.
WARMUP_WORK_SECONDS = 40.0
WARMUP_REST_SECONDS = 30.0
WARMUP_WORK_OVERRIDES = {
    "jumping_jacks": 60.0,
    "plank": 60.0,
}

WEEKS = [
    # sets, reps, pct, deload(omit accessory block)
    (3, 4, 0.75, False),
    (3, 4, 0.75, False),
    (4, 4, 0.80, False),
    (4, 4, 0.80, False),
    (4, 4, 0.80, False),
    (4, 3, 0.85, False),
    (4, 3, 0.85, False),
    (2, 4, 0.65, True),
]


def round_to_5(x):
    # round-half-up, not Python's banker's rounding, so e.g. 202.5 -> 205.
    return int(math.floor(x / 5 + 0.5)) * 5


# endregion

# region Garmin sport/step-type/condition/unit constants

STRENGTH_SPORT = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
STEP_TYPES = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "rest": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
}
COND_REPS = {"conditionTypeId": 10, "conditionTypeKey": "reps", "displayOrder": 10, "displayable": True}
COND_TIME = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
COND_ITERATIONS = {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False}
NO_TARGET = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
ZERO_STROKE = {"strokeTypeId": 0, "strokeTypeKey": None, "displayOrder": 0}
ZERO_EQUIPMENT = {"equipmentTypeId": 0, "equipmentTypeKey": None, "displayOrder": 0}
POUND = {"unitId": 9, "unitKey": "pound", "factor": 453.59237}

# endregion

# region step builders
# stepOrder runs global+sequential across the whole workout (repeat-group headers
# included); childStepId increments per repeat group, and every step inside a
# group carries its parent's. One Counters threaded through the builders holds both.


class Counters:
    def __init__(self):
        self.step_order = itertools.count(1)
        self.child_step_id = itertools.count(1)


# Fields every step carries; builders override only the ones that vary. Listed in
# the exact output order so {**_STEP_DEFAULTS, ...} preserves key order.
_STEP_DEFAULTS = {
    "type": "ExecutableStepDTO",
    "stepOrder": None,
    "stepType": None,
    "childStepId": None,
    "description": None,
    "endCondition": None,
    "endConditionValue": None,
    "targetType": NO_TARGET,
    "targetValueOne": None,
    "targetValueTwo": None,
    "targetValueUnit": None,
    "strokeType": ZERO_STROKE,
    "equipmentType": ZERO_EQUIPMENT,
    "category": None,
    "exerciseName": None,
    "weightValue": None,
    "weightUnit": None,
}


def exercise_step(counters, step_type, ex_key, end_condition, end_value, weight_lb=None, child_step_id=None):
    ref = EX[ex_key]
    return {
        **_STEP_DEFAULTS,
        "stepOrder": next(counters.step_order),
        "stepType": STEP_TYPES[step_type],
        "childStepId": child_step_id,
        "endCondition": end_condition,
        "endConditionValue": end_value,
        "category": ref.category,
        "exerciseName": ref.exercise_name,
        "weightValue": float(weight_lb) if weight_lb is not None else None,
        "weightUnit": POUND if weight_lb is not None else None,
    }


def rest_step(counters, seconds, child_step_id=None):
    return {
        **_STEP_DEFAULTS,
        "stepOrder": next(counters.step_order),
        "stepType": STEP_TYPES["rest"],
        "childStepId": child_step_id,
        "endCondition": COND_TIME,
        "endConditionValue": float(seconds),
    }


def repeat_group(counters, iterations, child_steps_fn, skip_last_rest=False):
    """child_steps_fn(child_id) -> list of steps already using that child_id."""
    group_order = next(counters.step_order)
    child_id = next(counters.child_step_id)
    steps = child_steps_fn(child_id)
    return {
        "type": "RepeatGroupDTO",
        "stepOrder": group_order,
        "stepType": STEP_TYPES["repeat"],
        "childStepId": child_id,
        "numberOfIterations": iterations,
        "workoutSteps": steps,
        "endConditionValue": float(iterations),
        "endCondition": COND_ITERATIONS,
        "skipLastRestStep": skip_last_rest,
        "smartRepeat": False,
    }


# endregion

# region workout assembly


def reps_step_duplicated_per_side(counters, step_type, ex_key, reps_per_side, child_step_id=None, weight_lb=None):
    """Unilateral movement -> two back-to-back rep steps (user chose: duplicate everywhere)."""
    return [
        exercise_step(
            counters,
            step_type,
            ex_key,
            COND_REPS,
            float(reps_per_side),
            weight_lb=weight_lb,
            child_step_id=child_step_id,
        ),
        exercise_step(
            counters,
            step_type,
            ex_key,
            COND_REPS,
            float(reps_per_side),
            weight_lb=weight_lb,
            child_step_id=child_step_id,
        ),
    ]


def build_warmup(counters, main_lift_key):
    # Every warmup move is a timed hold with a short rest before the next --
    # time-based throughout so the watch auto-advances (rep counting proved
    # unreliable on a real session). Default WARMUP_WORK_SECONDS, overridable
    # per exercise via WARMUP_WORK_OVERRIDES. Includes the empty-bar ramp.
    warmup_moves = [
        "jumping_jacks",
        "bodyweight_squat",
        "walking_lunge",
        "walking_lunge",
        "glute_bridge",
        "plank",
    ]
    steps = []
    for ex_key in warmup_moves:
        seconds = WARMUP_WORK_OVERRIDES.get(ex_key, WARMUP_WORK_SECONDS)
        steps.append(exercise_step(counters, "warmup", ex_key, COND_TIME, seconds))
        steps.append(rest_step(counters, WARMUP_REST_SECONDS))
    steps.append(
        repeat_group(
            counters,
            2,
            lambda cid: [
                exercise_step(counters, "warmup", main_lift_key, COND_TIME, WARMUP_WORK_SECONDS, child_step_id=cid),
                rest_step(counters, WARMUP_REST_SECONDS, child_step_id=cid),
            ],
        )
    )
    return steps


def build_sets(counters, ex_key, sets, reps, weight_lb, rest_sec):
    """One exercise: `sets` straight sets of `reps`, `rest_sec` rest between."""
    return [
        repeat_group(
            counters,
            sets,
            lambda cid: [
                exercise_step(
                    counters, "interval", ex_key, COND_REPS, float(reps), weight_lb=weight_lb, child_step_id=cid
                ),
                rest_step(counters, rest_sec, child_step_id=cid),
            ],
        )
    ]


def build_unilateral_day_a(counters, ex_key, weight_lb):
    # Loaded single-leg lift: 3 sets of 8/side (two back-to-back per-side rep
    # steps), 90s rest between sets. Variant (barbell/dumbbell) alternates by
    # session -- see main().
    return [
        repeat_group(
            counters,
            3,
            lambda cid: (
                reps_step_duplicated_per_side(counters, "interval", ex_key, 8, child_step_id=cid, weight_lb=weight_lb)
                + [rest_step(counters, 90, child_step_id=cid)]
            ),
        )
    ]


def build_accessory_day_a(counters):
    def children(cid):
        steps = [
            exercise_step(counters, "interval", "barbell_row", COND_REPS, 8.0, child_step_id=cid),
            rest_step(counters, 30, child_step_id=cid),
        ]
        steps += [
            exercise_step(counters, "interval", "push_up", COND_REPS, 12.0, child_step_id=cid),
            rest_step(counters, 30, child_step_id=cid),
        ]
        steps += [exercise_step(counters, "interval", "barbell_rdl", COND_REPS, 8.0, child_step_id=cid)]
        steps.append(rest_step(counters, 60, child_step_id=cid))
        return steps

    return [repeat_group(counters, 2, children, skip_last_rest=True)]


def build_accessory_day_b(counters):
    def children(cid):
        steps = reps_step_duplicated_per_side(counters, "interval", "rfe_split_squat", 8, child_step_id=cid)
        steps.append(rest_step(counters, 30, child_step_id=cid))
        steps += reps_step_duplicated_per_side(counters, "interval", "single_arm_db_row", 8, child_step_id=cid)
        steps.append(rest_step(counters, 30, child_step_id=cid))
        steps += [exercise_step(counters, "interval", "db_floor_press", COND_REPS, 8.0, child_step_id=cid)]
        steps.append(rest_step(counters, 60, child_step_id=cid))
        return steps

    return [repeat_group(counters, 2, children, skip_last_rest=True)]


def build_workout(
    name,
    warmup_lift_key,
    power_ex_key,
    power_reps,
    power_weight_lb,
    main_ex_key,
    sets,
    reps,
    weight_lb,
    accessory_fn,
    deload,
    unilateral_fn=None,
):
    counters = Counters()
    steps = []
    steps += build_warmup(counters, warmup_lift_key)
    steps += build_sets(counters, power_ex_key, 3, power_reps, power_weight_lb, 90)
    steps += build_sets(counters, main_ex_key, sets, reps, weight_lb, 120)
    if not deload:
        if unilateral_fn:
            steps += unilateral_fn(counters)
        steps += accessory_fn(counters)

    return {
        "workoutName": name,
        "description": None,
        "sportType": STRENGTH_SPORT,
        "subSportType": None,
        "estimatedDurationInSecs": 0,
        "estimatedDistanceInMeters": 0.0,
        "avgTrainingSpeed": 0.0,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": STRENGTH_SPORT,
                "workoutSteps": steps,
            }
        ],
    }


def validate(workout):
    steps = workout["workoutSegments"][0]["workoutSteps"]
    seen_orders = []

    def walk(step_list):
        for s in step_list:
            seen_orders.append(s["stepOrder"])
            if s["type"] == "RepeatGroupDTO":
                assert s["numberOfIterations"] == s["endConditionValue"], s
                walk(s["workoutSteps"])

    walk(steps)
    assert seen_orders == list(range(1, len(seen_orders) + 1)), f"stepOrder not sequential: {seen_orders}"


def main():
    out_dir = WORKSPACE_ROOT / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, (sets, reps, pct, deload) in enumerate(WEEKS, start=1):
        squat_weight = round_to_5(SQUAT_1RM * pct)
        deadlift_weight = round_to_5(DEADLIFT_1RM * pct)
        split_ex, split_weight = SPLIT_SQUAT_VARIANTS[(i - 1) % len(SPLIT_SQUAT_VARIANTS)]

        day_a = build_workout(
            f"Week {i} Day A - Squat",
            warmup_lift_key="empty_bar_squat",
            power_ex_key="db_jump_squat",
            power_reps=5,
            power_weight_lb=10,
            main_ex_key="barbell_back_squat",
            sets=sets,
            reps=reps,
            weight_lb=squat_weight,
            accessory_fn=build_accessory_day_a,
            unilateral_fn=lambda counters, k=split_ex, w=split_weight: build_unilateral_day_a(counters, k, w),
            deload=deload,
        )
        day_b = build_workout(
            f"Week {i} Day B - Deadlift",
            warmup_lift_key="empty_bar_deadlift",
            power_ex_key="broad_jump",
            power_reps=5,
            power_weight_lb=10,
            main_ex_key="barbell_deadlift",
            sets=sets,
            reps=reps,
            weight_lb=deadlift_weight,
            accessory_fn=build_accessory_day_b,
            deload=deload,
        )
        validate(day_a)
        validate(day_b)

        (out_dir / f"week{i}-dayA.json").write_text(json.dumps(day_a, indent=2))
        (out_dir / f"week{i}-dayB.json").write_text(json.dumps(day_b, indent=2))

        logger.info(
            "week %d: squat %d lb, deadlift %d lb, %dx%d%s",
            i,
            squat_weight,
            deadlift_weight,
            sets,
            reps,
            " (deload)" if deload else "",
        )


# endregion


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    main()
