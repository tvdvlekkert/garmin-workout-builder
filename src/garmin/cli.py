"""Wrapper CLI for pushing workout JSON to Garmin Connect.

Auth: garth (pinned to 0.6.3 -- see src/garmin/client.py for why). A session is
resumed from secrets/garth_session/ when present and still valid, otherwise
you're prompted for email/password/MFA on stdin and the new session is saved.
Run `auth` to force a fresh login.

GET, POST (create), and PUT (update) are confirmed working against real Garmin
Connect. DELETE and schedule are still INFERRED, not yet verified. Every
mutating command defaults to a dry run (prints the request instead of sending
it); pass --live to actually send it.
"""

import argparse
import json
import logging
import sys

from garmin.client import GarminClient
from workspace import workspace_root

logger = logging.getLogger(__name__)


class WorkoutClient:
    """Garmin workout-service commands over a lazily-authenticated garth client.

    Each public method is a CLI subcommand and takes the parsed argparse
    namespace. The garth client is created on first use, so `auth` and dry-run
    commands that never touch the network don't trigger a login.
    """

    BASE = "/workout-service"

    # Server-assigned fields; sending them on create/update 400s or clobbers.
    # childStepId is NOT one -- it's repeat-group linkage, not a server ID.
    FORBIDDEN_FIELDS = {"workoutId", "ownerId", "author", "createdDate", "updatedDate", "stepId"}

    def __init__(self):
        self._garmin = GarminClient()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = self._garmin.ensure()
        return self._client

    # region subcommands

    def auth(self, args):
        self._garmin.login()

    def types(self, args):
        data = self.client.connectapi(f"{self.BASE}/workout/types")
        path = workspace_root() / "ref" / "workout-types.json"
        path.write_text(json.dumps(data, indent=2))
        logger.info("saved to %s", path)

    def get(self, args):
        result = self.client.connectapi(f"{self.BASE}/workout/{args.workout_id}")
        if result is not None:
            logger.info(json.dumps(result, indent=2))

    def list(self, args):
        params = {"start": 0, "limit": args.limit, "myWorkoutsOnly": "true"}
        result = self.client.connectapi(f"{self.BASE}/workouts", params=params)
        for w in result or []:
            logger.info("%s\t%s", w.get("workoutId"), w.get("workoutName"))

    def create(self, args):
        payload = self._strip(self._load(args.file))
        result = self._mutate("POST", f"{self.BASE}/workout", payload, args.live)
        self._report("create", args.live, result)

    def update(self, args):
        payload = self._strip(self._load(args.file))
        result = self._mutate("PUT", f"{self.BASE}/workout/{args.workout_id}", payload, args.live)
        self._report("update", args.live, result)

    def delete(self, args):
        result = self._mutate("DELETE", f"{self.BASE}/workout/{args.workout_id}", None, args.live)
        self._report("delete", args.live, result)

    def schedule(self, args):
        result = self._mutate("POST", f"{self.BASE}/schedule/{args.workout_id}", {"date": args.date}, args.live)
        self._report("schedule", args.live, result)

    # endregion

    # region helpers

    def _mutate(self, method, path, body, live):
        """Send a mutating request, or preview it on a dry run (the default)."""
        if not live:
            self._describe(method, path, body)
            return None
        kwargs = {"json": body} if body is not None else {}
        return self.client.connectapi(path, method=method, **kwargs)

    @staticmethod
    def _load(file):
        return json.loads((workspace_root() / file).read_text())

    @classmethod
    def _strip(cls, obj):
        if isinstance(obj, dict):
            return {k: cls._strip(v) for k, v in obj.items() if k not in cls.FORBIDDEN_FIELDS}
        if isinstance(obj, list):
            return [cls._strip(v) for v in obj]
        return obj

    @staticmethod
    def _describe(method, path, body):
        logger.info("[dry run] %s %s", method, path)
        if body is not None:
            logger.info("  body: %s", json.dumps(body, indent=2))

    @staticmethod
    def _report(action, live, result):
        """Confirm a live mutation succeeded (connectapi raises on non-2xx, so
        reaching here means success). Surface the workoutId when the response
        carries one; dry runs stay silent -- _mutate already printed the preview.
        """
        if not live:
            return
        workout_id = result.get("workoutId") if isinstance(result, dict) else None
        if workout_id is not None:
            logger.info("%s ok -- workoutId %s", action, workout_id)
        else:
            logger.info("%s ok", action)

    # endregion


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    client = WorkoutClient()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(required=True)

    sub.add_parser("auth", help="force a fresh interactive login, overwriting the saved session").set_defaults(run=client.auth)

    sub.add_parser("types", help="fetch the workout-step enum catalog, save to ref/workout-types.json").set_defaults(run=client.types)

    p = sub.add_parser("get", help="fetch a workout by id")
    p.add_argument("workout_id")
    p.set_defaults(run=client.get)

    p = sub.add_parser("list", help="list your workouts (id + name) to discover ids")
    p.add_argument("--limit", type=int, default=100, help="max workouts to fetch (default: 100)")
    p.set_defaults(run=client.list)

    p = sub.add_parser("create", help="POST a new workout from a JSON file")
    p.add_argument("file")
    p.add_argument("--live", action="store_true", help="actually send the request (default: dry run)")
    p.set_defaults(run=client.create)

    p = sub.add_parser("update", help="PUT an existing workout")
    p.add_argument("workout_id")
    p.add_argument("file")
    p.add_argument("--live", action="store_true")
    p.set_defaults(run=client.update)

    p = sub.add_parser("delete", help="DELETE a workout")
    p.add_argument("workout_id")
    p.add_argument("--live", action="store_true")
    p.set_defaults(run=client.delete)

    p = sub.add_parser("schedule", help="schedule a workout to a calendar date")
    p.add_argument("workout_id")
    p.add_argument("date", help="YYYY-MM-DD")
    p.add_argument("--live", action="store_true")
    p.set_defaults(run=client.schedule)

    args = parser.parse_args()
    args.run(args)
