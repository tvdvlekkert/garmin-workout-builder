"""Authenticated Garmin Connect client, via garth.

GarminClient is a thin wrapper: ensure() hands back garth's own client,
resuming a cached session when possible and falling back to an interactive
login.

Session (OAuth1 + OAuth2 tokens) is cached as JSON in secrets/garth_session/
via garth's own dump()/load(). ensure() resumes it and probes a cheap endpoint
to confirm it's still live -- a resumed OAuth1 token can be dead/revoked with
no local signal otherwise -- and falls back to an interactive login (prompting
for email/password/MFA on stdin) when it isn't.
"""

import getpass
import logging

import garth

from workspace import workspace_root

logger = logging.getLogger(__name__)


class GarminClient:
    """Produces an authenticated garth client."""

    def __init__(self, session_dir=None):
        self._session_dir = session_dir

    @property
    def session_dir(self):
        # Lazy: workspace_root() shells out to git outside Bazel, so resolving
        # it eagerly (especially at import) breaks a bare sandbox / tests.
        if self._session_dir is None:
            self._session_dir = workspace_root() / "secrets" / "garth_session"
        return self._session_dir

    def ensure(self):
        """Return an authenticated garth client, resuming a saved session if
        it's still valid and prompting an interactive login otherwise."""
        if (self.session_dir / "oauth2_token.json").exists():
            try:
                garth.resume(self.session_dir)
                # resume() only reads disk; probe a cheap endpoint to catch a
                # dead OAuth1 token now rather than mid-command (raises on non-2xx).
                garth.client.connectapi("/userprofile-service/userprofile/user-settings")
                return garth.client
            except Exception:
                pass
        self.login()
        return garth.client

    def login(self):
        """Interactive login (email/password/MFA on stdin); caches the session."""
        email = input("Garmin email: ").strip()
        password = getpass.getpass("Garmin password: ")
        garth.login(email, password)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        garth.save(self.session_dir)
        logger.info("session saved to %s", self.session_dir)
