"""Authentication credentials for Mixpanel API."""

from typing import Union

from requests.auth import HTTPBasicAuth


class ServiceAccountCredentials:
    """Service account credentials for server-to-server authentication.

    :param str username: Service account username
    :param str secret: Service account secret

    Both username and secret are required. Use these credentials for enhanced
    security in server-to-server integrations as an alternative to API secrets.

    Example::

        from mixpanel import Mixpanel, ServiceAccountCredentials

        credentials = ServiceAccountCredentials(
            username='your-service-account-username',
            secret='your-service-account-secret'
        )
        mp = Mixpanel('YOUR_TOKEN', credentials=credentials)
    """

    def __init__(self, username: str, secret: str):
        if not username:
            raise ValueError("Service account username cannot be empty")
        if not secret:
            raise ValueError("Service account secret cannot be empty")

        self.username = username
        self.secret = secret

    def to_http_basic_auth(self) -> HTTPBasicAuth:
        """Convert credentials to HTTPBasicAuth for requests."""
        return HTTPBasicAuth(self.username, self.secret)

    def __repr__(self) -> str:
        return f"ServiceAccountCredentials(username={self.username!r}, secret='***')"


class APISecretCredentials:
    """API secret credentials for authenticating import and merge operations.

    :param str api_secret: Your Mixpanel project's API secret

    .. deprecated:: 5.2.0
        Use :class:`~.ServiceAccountCredentials` for enhanced security.
        API secrets will continue to be supported for backward compatibility.

    Example::

        from mixpanel import Mixpanel, APISecretCredentials

        credentials = APISecretCredentials(api_secret='YOUR_API_SECRET')
        mp = Mixpanel('YOUR_TOKEN', credentials=credentials)

        # Use for import operations
        mp.import_data(api_key='PROJECT_ID', data=event)
    """

    def __init__(self, api_secret: str):
        if not api_secret:
            raise ValueError("API secret cannot be empty")

        self.api_secret = api_secret

    def to_http_basic_auth(self) -> HTTPBasicAuth:
        """Convert credentials to HTTPBasicAuth for requests.

        API secrets use the secret as username with empty password.
        """
        return HTTPBasicAuth(self.api_secret, "")

    def __repr__(self) -> str:
        return "APISecretCredentials(api_secret='***')"


# Type alias for supported credential types
MixpanelCredentials = Union[ServiceAccountCredentials, APISecretCredentials]
