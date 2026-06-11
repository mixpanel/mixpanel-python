"""Authentication credentials for Mixpanel API."""

from requests.auth import HTTPBasicAuth


class ServiceAccountCredentials:
    """Service account credentials for server-to-server authentication.

    :param str username: Service account username
    :param str secret: Service account secret
    :param str project_id: Mixpanel project ID

    All parameters are required. Use these credentials for enhanced
    security in server-to-server integrations.

    .. note::
        Service account authentication is the recommended method for server-side
        integrations. It provides better security than API secrets by using
        unique username/secret pairs instead of a single shared secret.

    Example::

        from mixpanel import Mixpanel, ServiceAccountCredentials

        credentials = ServiceAccountCredentials(
            username='your-service-account-username',
            secret='your-service-account-secret',
            project_id='123456'
        )
        mp = Mixpanel('YOUR_TOKEN', credentials=credentials)
    """

    def __init__(self, username: str, secret: str, project_id: str):
        if not username or not username.strip():
            raise ValueError("Service account username cannot be empty")
        if not secret or not secret.strip():
            raise ValueError("Service account secret cannot be empty")
        if not project_id or not project_id.strip():
            raise ValueError("Service account project_id cannot be empty")

        self.username = username.strip()
        self.secret = secret.strip()
        self.project_id = project_id.strip()

    def to_http_basic_auth(self) -> HTTPBasicAuth:
        """Convert credentials to HTTPBasicAuth for requests."""
        return HTTPBasicAuth(self.username, self.secret)

    def __repr__(self) -> str:
        return f"ServiceAccountCredentials(username={self.username!r}, project_id={self.project_id!r}, secret='***')"
