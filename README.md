# garmin-workout-builder

Generates an 8-week strength training progression (Day A: squat, Day B:
deadlift) as Garmin Connect workout JSON, and pushes it to Garmin Connect.

## Layout

- `src/generate_workouts.py` -- builds `out/week{1-8}-day{A,B}.json`. Pure
  local computation, no network access. Progression, exercise mapping, and
  weight rounding live here.
- `src/garmin/cli.py` -- CLI for reading/writing workouts on Garmin Connect
  (`types`, `get`, `list`, `create`, `update`, `delete`, `schedule`, `auth`).
- `src/garmin/client.py` -- garth-based authenticated client used by `cli.py`.
- `ref/Exercises.json` -- Garmin's public exercise catalog, used to
  cross-check `EX` mappings in `generate_workouts.py`.
- `ref/workout-types.json` -- workout-step enum catalog, fetched via
  `bazel run //:garmin_push -- types` (the authenticated
  `workout-service/workout/types` endpoint).
- `secrets/garth_session/` -- gitignored. Cached OAuth1/OAuth2 tokens so you
  don't have to log in on every run.

## Setup

Prerequisites are Bazel (via [bazelisk](https://github.com/bazelbuild/bazelisk))
and git-lfs (to fetch the LFS-tracked `MODULE.bazel.lock`) -- see
[INSTALL.md](INSTALL.md) for Homebrew and no-Homebrew install steps. Everything
else (the Python 3.12 toolchain, pip dependencies, and uv itself) is fetched
hermetically by Bazel.

`MODULE.bazel` pins the Python toolchain to 3.12 and locks dependencies from
`requirements.txt`. When `requirements.in` changes, regenerate the lock file
with `bazel run //:requirements.update` (this drives uv via
[rules_uv](https://github.com/bazel-contrib/rules_uv) -- no system uv needed).
`bazel test //:requirements_test` checks that the lock is up to date.

Auth is handled by [garth](https://github.com/matin/garth), pinned to `0.6.3`
in `requirements.in`.

## Usage

```
bazel run //:generate_workouts

bazel run //:garmin_push -- auth
bazel run //:garmin_push -- types
bazel run //:garmin_push -- list
bazel run //:garmin_push -- list --limit 200
bazel run //:garmin_push -- get <workout-id>
bazel run //:garmin_push -- create out/week1-dayA.json
bazel run //:garmin_push -- create out/week1-dayA.json --live
bazel run //:garmin_push -- schedule <workout-id> 2026-07-21 --live
```

Every mutating command (`create`, `update`, `delete`, `schedule`) defaults to
a dry run -- it prints the request instead of sending it. Pass `--live` to
actually send it.

`get`/`types` are confirmed working against real Garmin Connect.
`create`/`update`/`delete`/`schedule` are inferred from the workout-service
API shape but not yet verified live -- confirm one with `--live` before
trusting the rest.
