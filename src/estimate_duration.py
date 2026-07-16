"""Estimates how long a generated workout takes to complete.

Reads a workout JSON file (the same shape generate_workouts.py writes) and
sums three things: exercise work time, prescribed rest, and a fixed
per-exercise transition overhead. Reports the total both as-prescribed (every
rest timer honored) and with rests skipped (a floor).

The per-rep tempos below are deliberately rough -- they're a planning aid, not
a stopwatch. Loaded lifts get a small fixed setup add-on (unrack/position).

Run:
    bazel run //:estimate_duration -- out/week1-dayA.json
    bazel run //:estimate_duration                 # all out/week*.json
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from workspace import workspace_root

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = workspace_root()

# Rough seconds-per-rep by movement. Unknown exercises fall back to 3.0.
SEC_PER_REP = {
    "SQUAT": 3.0,
    "LUNGE": 2.5,
    "HIP_RAISE": 2.5,
    "DEAD_BUG": 3.0,
    "BARBELL_BACK_SQUAT": 4.0,
    "BARBELL_DEADLIFT": 4.0,
    "DUMBBELL_JUMP_SQUAT": 2.5,
    "BARBELL_ROW": 3.0,
    "PUSH_UP": 2.0,
    "ROMANIAN_DEADLIFT": 4.0,
}
DEFAULT_SEC_PER_REP = 3.0

# Loaded lifts get a fixed setup add-on per set (unrack, position, brace).
LOADED = {"BARBELL_BACK_SQUAT", "BARBELL_DEADLIFT", "DUMBBELL_JUMP_SQUAT", "BARBELL_ROW", "ROMANIAN_DEADLIFT"}
LOADED_SETUP_SEC = 8.0

# Grab equipment / read the watch between every non-rest step.
TRANSITION_SEC = 10.0


def _step_work_and_rest(step):
    """Return (work_seconds, rest_seconds) for a single executable step."""
    if step["stepType"]["stepTypeKey"] == "rest":
        return 0.0, step["endConditionValue"]
    if step["endCondition"]["conditionTypeKey"] == "time":
        return step["endConditionValue"], 0.0
    ex = step.get("exerciseName")
    reps = step["endConditionValue"]
    work = reps * SEC_PER_REP.get(ex, DEFAULT_SEC_PER_REP)
    if ex in LOADED:
        work += LOADED_SETUP_SEC
    return work, 0.0


def estimate(workout):
    """Return a dict of minute totals for a parsed workout."""
    work = rest = n_exercises = 0.0

    def walk(step_list, mult):
        nonlocal work, rest, n_exercises
        for s in step_list:
            if s["type"] == "RepeatGroupDTO":
                walk(s["workoutSteps"], mult * s["numberOfIterations"])
            else:
                w, r = _step_work_and_rest(s)
                work += w * mult
                rest += r * mult
                if s["stepType"]["stepTypeKey"] != "rest":
                    n_exercises += mult

    walk(workout["workoutSegments"][0]["workoutSteps"], 1)
    transition = n_exercises * TRANSITION_SEC
    return {
        "work_min": work / 60,
        "rest_min": rest / 60,
        "transition_min": transition / 60,
        "total_prescribed_min": (work + rest + transition) / 60,
        "total_rests_skipped_min": (work + transition) / 60,
    }


def main(args):
    if args.files:
        paths = [WORKSPACE_ROOT / f for f in args.files]
    else:
        paths = sorted((WORKSPACE_ROOT / "out").glob("week*.json"))
        if not paths:
            sys.exit("no out/week*.json found -- run generate_workouts first")

    for path in paths:
        workout = json.loads(Path(path).read_text())
        e = estimate(workout)
        logger.info("%s  (%s)", workout["workoutName"], path)
        logger.info("  work:               %5.1f min", e["work_min"])
        logger.info("  prescribed rest:    %5.1f min", e["rest_min"])
        logger.info("  transitions:        %5.1f min", e["transition_min"])
        logger.info("  TOTAL prescribed:   %5.1f min", e["total_prescribed_min"])
        logger.info("  TOTAL rests skipped:%5.1f min", e["total_rests_skipped_min"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "files",
        nargs="*",
        help="workout JSON file(s) to estimate; defaults to all out/week*.json",
    )
    main(parser.parse_args())
