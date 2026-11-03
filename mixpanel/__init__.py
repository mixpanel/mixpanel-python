"""This is the official Mixpanel client library for Python.

Mixpanel client libraries allow for tracking events and setting properties on
People Analytics profiles from your server-side projects. This is the API
documentation; you may also be interested in the higher-level `usage
documentation`_. If your users are interacting with your application via the
web, you may also be interested in our `JavaScript library`_.

.. _`JavaScript library`: https://developer.mixpanel.com/docs/javascript
.. _`usage documentation`: https://developer.mixpanel.com/docs/python

:class:`~.Mixpanel` is the primary class for tracking events and sending People
Analytics updates. :class:`~.Consumer` and :class:`~.BufferedConsumer` allow
callers to customize the IO characteristics of their tracking.
"""

import copy
import datetime
import json
import logging
import time
import uuid
from typing import Optional

import requests
import urllib3
from requests.auth import HTTPBasicAuth

from .credentials import ServiceAccountCredentials
from .flags.local_feature_flags import LocalFeatureFlagsProvider
from .flags.remote_feature_flags import RemoteFeatureFlagsProvider
from .flags.types import LocalFlagsConfig, RemoteFlagsConfig
from .identity import MixpanelIdentity, _parse_combined_distinct_id

__version__ = "5.4.1"

logger = logging.getLogger(__name__)

# Hierarchical groups user profiles are group profiles, and /groups has no
# $add, $append or $merge.
GROUP_OPERATIONS = ("$set", "$set_once", "$unset", "$union", "$remove", "$delete")

# Keys of a /engage or /groups message that are not operations.
_PEOPLE_NON_OPERATION_KEYS = frozenset(
    (
        "$token",
        "$time",
        "$distinct_id",
        "$ip",
        "$ignore_time",
        "$ignore_alias",
        "$latitude",
        "$longitude",
    )
)
_GROUP_NON_OPERATION_KEYS = frozenset(
    (
        "$token",
        "$time",
        "$group_key",
        "$group_id",
        "$company_id",
        "$ip",
        "$ignore_time",
        "$ignore_alias",
        "$latitude",
        "$longitude",
    )
)


def _unsupported_operations(message, non_operation_keys):
    """Return the $-prefixed operation keys of ``message`` that /groups lacks."""
    return [
        key
        for key in message
        if isinstance(key, str)
        and key.startswith("$")
        and key not in non_operation_keys
        and key not in GROUP_OPERATIONS
    ]


class DatetimeSerializer(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            fmt = "%Y-%m-%dT%H:%M:%S"
            return obj.strftime(fmt)

        return json.JSONEncoder.default(self, obj)


def json_dumps(data, cls=None):
    # Separators are specified to eliminate whitespace.
    return json.dumps(data, separators=(",", ":"), cls=cls)


class Mixpanel:
    """Instances of Mixpanel are used for all events and profile updates.

    :param str token: your project's Mixpanel token
    :param consumer: can be used to alter the behavior of tracking (default
        :class:`~.Consumer`)
    :param json.JSONEncoder serializer: a JSONEncoder subclass used to handle
        JSON serialization (default :class:`~.DatetimeSerializer`)
    :param ServiceAccountCredentials credentials: Optional service account
        credentials for authentication. Recommended for server-side integrations.
    :param bool hierarchical_groups: True if the project uses hierarchical
        groups (default False). See below.

    See `Built-in consumers`_ for details about the consumer interface.

    **Hierarchical groups.** When ``hierarchical_groups`` is True, Mixpanel
    builds the distinct id from ``$user_id`` and ``$company_id``. Pass a
    :class:`~.MixpanelIdentity` wherever a ``distinct_id`` is accepted to send
    those properties. On events a plain distinct id still works, and Mixpanel
    accepts a distinct id it built itself (``$company:{company}|$user:{user}``),
    but any other distinct id names a different user that nothing reconciles
    later.

    User profiles are group profiles keyed by ``$user_id``, and nothing is sent
    to ``/engage``. A user profile update takes an identity with a user and a
    company, or a distinct id of the form ``$company:{company}|$user:{user}``,
    which is sent to ``/groups`` as that company and user; any other distinct
    id raises ``ValueError``. User profiles support only what ``/groups``
    supports: ``people_increment``, ``people_append``,
    ``people_track_charge`` and ``people_clear_charges`` raise
    :class:`~.UnsupportedOperationError`, while
    ``people_set`` and its siblings address a profile from an identity without
    needing a distinct id. Group profile updates require a known company,
    either through :meth:`for_company` or a ``$company_id`` in ``meta``, and
    raise :class:`~.CompanyRequiredError` otherwise.

    Events are sent identically in both modes, and so are group profile
    updates that are valid in both.

    .. versionadded:: 4.2.0
        The *serializer* parameter.
    """

    def __init__(
        self,
        token,
        consumer=None,
        serializer=DatetimeSerializer,
        local_flags_config: Optional[LocalFlagsConfig] = None,
        remote_flags_config: Optional[RemoteFlagsConfig] = None,
        credentials: Optional[ServiceAccountCredentials] = None,
        hierarchical_groups: bool = False,
    ):
        self._token = token
        self._credentials = credentials
        self._hierarchical_groups = hierarchical_groups
        self._company_id = None

        # Warn if credentials are provided but won't be used due to custom consumer
        if consumer is not None and credentials is not None:
            logger.warning(
                "Credentials passed to Mixpanel() are ignored when a custom consumer is provided. "
                "Pass credentials to your consumer's constructor instead: "
                "Consumer(credentials=...)"
            )

        self._consumer = consumer or Consumer(credentials=credentials)
        self._serializer = serializer

        self._local_flags_provider = None
        self._remote_flags_provider = None

        if local_flags_config:
            self._local_flags_provider = LocalFeatureFlagsProvider(
                self._token,
                local_flags_config,
                __version__,
                self.track,
                credentials,
                hierarchical_groups=hierarchical_groups,
            )

        if remote_flags_config:
            self._remote_flags_provider = RemoteFeatureFlagsProvider(
                self._token,
                remote_flags_config,
                __version__,
                self.track,
                credentials,
                hierarchical_groups=hierarchical_groups,
            )

    def for_company(self, company_id):
        """Return a client that adds ``$company_id`` to every group profile update.

        :param str company_id: the id of the top-level company
        :raises ValueError: if ``company_id`` is empty or None

        Hierarchical groups projects require ``$company_id`` on every
        ``/groups`` write, including the company's own profile and user
        profiles::

            acme = mp.for_company('acme')
            acme.company_set(company_properties)
            acme.group_set('$user_id', 'user_123', user_properties)
            acme.group_set('department', 'finance', department_properties)

        The ``company_*`` methods update the bound company's own profile: each
        is the matching ``group_*`` method with ``('$company_id', company_id)``.

        The returned client shares this client's consumer, serializer and flag
        providers; this client is unchanged. The bound company is sent as a
        top-level ``$company_id`` and wins over a ``$company_id`` in ``meta``.
        It does not apply to user profile updates made with a
        :class:`~.MixpanelIdentity`, which use the identity's own company.
        """
        if not company_id:
            raise ValueError("company_id must be non-empty")
        bound = copy.copy(self)
        bound._company_id = company_id  # noqa: SLF001
        return bound

    def _require_identity_matches_project(self, identity):
        """Reject an identity that this client's project would mis-attribute.

        Hierarchical groups is a project setting, and ingestion accepts the
        identity keys on any project but ignores them, so a mismatch would be
        silently mis-attributed.
        """
        if identity is None:
            raise ValueError("identity must not be None")
        if identity.is_hierarchical and not self._hierarchical_groups:
            msg = (
                f"{identity!r} requires a hierarchical groups client: "
                "Mixpanel(token, hierarchical_groups=True)"
            )
            raise ValueError(msg)
        # The company is part of a hierarchical user's identity. A $user_id sent
        # without one resolves to a separate user that nothing reconciles later.
        # A device id rescues that case: Mixpanel keeps the event under the
        # device and links it to the company-scoped user once a later event
        # carries all three.
        if (
            self._hierarchical_groups
            and identity.user_id is not None
            and identity.company_id is None
            and identity.device_id is None
        ):
            msg = (
                f"{identity!r} needs a company on a hierarchical groups project. "
                "A user id sent without one, and without a device id, names a "
                "separate user that cannot be merged afterwards."
            )
            raise ValueError(msg)

    def _event_properties(self, distinct_id, event_time, properties):
        """Build event properties for a distinct id or a MixpanelIdentity."""
        identity = None
        if isinstance(distinct_id, MixpanelIdentity):
            identity = distinct_id
            self._require_identity_matches_project(identity)
            distinct_id = identity.distinct_id

        all_properties = {"token": self._token}
        if identity is None or distinct_id is not None:
            all_properties["distinct_id"] = distinct_id
        all_properties.update(
            {
                "time": event_time,
                "$insert_id": self._make_insert_id(),
                "mp_lib": "python",
                "$lib_version": __version__,
            }
        )
        if properties:
            all_properties.update(properties)
        if identity is not None:
            identity._apply_to(all_properties)  # noqa: SLF001
        return all_properties

    def _now(self):
        return time.time()

    def _make_insert_id(self):
        return uuid.uuid4().hex

    @property
    def local_flags(self) -> LocalFeatureFlagsProvider:
        """Get the local flags provider if configured for it."""
        if self._local_flags_provider is None:
            raise MixpanelException(
                "No local flags provider initialized. Pass local_flags_config to constructor."
            )
        return self._local_flags_provider

    @property
    def remote_flags(self) -> RemoteFeatureFlagsProvider:
        """Get the remote flags provider if configured for it."""
        if self._remote_flags_provider is None:
            raise MixpanelException(
                "No remote_flags_config was passed to the constructor"
            )
        return self._remote_flags_provider

    def track(self, distinct_id, event_name, properties=None, meta=None):
        """Record an event.

        :param distinct_id: identifies the user triggering the event
        :type distinct_id: str or MixpanelIdentity
        :param str event_name: a name describing the event
        :param dict properties: additional data to record; keys should be
            strings, and values should be strings, numbers, or booleans
        :param dict meta: overrides Mixpanel special properties
        :raises ValueError: if a :class:`~.MixpanelIdentity` does not suit
            this project

        ``properties`` should describe the circumstances of the event, or
        aspects of the source or user associated with it. ``meta`` is used
        (rarely) to override special values sent in the event object.

        For a :class:`~.MixpanelIdentity`, its keys replace any values for the
        same keys in ``properties``, and ``distinct_id`` is sent only if the
        identity has one.
        """
        all_properties = self._event_properties(distinct_id, self._now(), properties)
        event = {
            "event": event_name,
            "properties": all_properties,
        }
        if meta:
            event.update(meta)
        self._consumer.send("events", json_dumps(event, cls=self._serializer))

    def import_data(
        self,
        api_key,
        distinct_id,
        event_name,
        timestamp,
        properties=None,
        meta=None,
        api_secret=None,
    ):
        """Record an event that occurred more than 5 days in the past.

        :param str api_key: (DEPRECATED) your Mixpanel project's API key
        :param distinct_id: identifies the user triggering the event; see
            :meth:`track` for passing a :class:`~.MixpanelIdentity`
        :type distinct_id: str or MixpanelIdentity
        :param str event_name: a name describing the event
        :param int timestamp: UTC seconds since epoch
        :param dict properties: additional data to record; keys should be
            strings, and values should be strings, numbers, or booleans
        :param dict meta: overrides Mixpanel special properties
        :param str api_secret: (DEPRECATED) Your Mixpanel project's API secret.

        .. deprecated::
            Both *api_key* and *api_secret* parameters are deprecated. Use
            :class:`~.ServiceAccountCredentials` with the *credentials* parameter
            instead for enhanced security. Legacy authentication will continue to work
            for backward compatibility but will be removed in a future major version.

        .. versionadded:: 4.8.0
            The *api_secret* parameter.

        .. note::
            **Recommended**: Use ServiceAccountCredentials for authentication:

            .. code-block:: python

                credentials = ServiceAccountCredentials(
                    username='YOUR_SERVICE_ACCOUNT_USERNAME',
                    secret='YOUR_SERVICE_ACCOUNT_SECRET',
                    project_id='YOUR_PROJECT_ID'
                )
                mp = Mixpanel(YOUR_TOKEN, credentials=credentials)
                mp.import_data(
                    api_key=None,
                    distinct_id='user123',
                    event_name='Signup',
                    timestamp=1000000000,
                    properties={'source': 'email'}
                )

        To avoid accidentally recording invalid events, the Mixpanel API's
        ``track`` endpoint disallows events that occurred too long ago. This
        method can be used to import such events. See our online documentation
        for `more details
        <https://developer.mixpanel.com/reference/events#import-events>`__.
        """
        if api_secret is not None:
            logger.warning(
                "api_secret is deprecated and will be removed in a future version. "
                "Please migrate to ServiceAccountCredentials for enhanced security."
            )
        if api_key is not None:
            logger.warning(
                "api_key is deprecated and will be removed in a future version. "
                "Please migrate to ServiceAccountCredentials for enhanced security."
            )

        all_properties = self._event_properties(distinct_id, timestamp, properties)
        event = {
            "event": event_name,
            "properties": all_properties,
        }
        if meta:
            event.update(meta)

        self._consumer.send(
            "imports", json_dumps(event, cls=self._serializer), (api_key, api_secret)
        )

    def alias(self, alias_id, original, meta=None):
        """Creates an alias which Mixpanel will use to remap one id to another.

        :param str alias_id: A distinct_id to be merged with the original
            distinct_id. Each alias can only map to one distinct_id.
        :param str original: A distinct_id to be merged with alias_id.
        :param dict meta: overrides Mixpanel special properties

        Immediately creates a one-way mapping between two ``distinct_ids``.
        Events triggered by the new id will be associated with the existing
        user's profile and behavior. See our online documentation for `more
        details
        <https://developer.mixpanel.com/reference/identities#identity-create-alias>`__.

        .. note::
            Calling this method *always* results in a synchronous HTTP request
            to Mixpanel servers, regardless of any custom consumer.

        :raises UnsupportedOperationError: on a hierarchical groups client
        """
        if self._hierarchical_groups:
            msg = (
                "alias is not supported for hierarchical groups projects, which "
                "identify a user by company and user id. Track with a "
                "MixpanelIdentity(user_id=..., company_id=...) instead."
            )
            raise UnsupportedOperationError(msg)
        event = {
            "event": "$create_alias",
            "properties": {
                "distinct_id": original,
                "alias": alias_id,
                "token": self._token,
            },
        }
        if meta:
            event.update(meta)

        sync_consumer = Consumer()
        sync_consumer.send("events", json_dumps(event, cls=self._serializer))

    def merge(self, api_key, distinct_id1, distinct_id2, meta=None, api_secret=None):
        """Merges the two given distinct_ids.

        :param str api_key: (DEPRECATED) Your Mixpanel project's API key.
        :param str distinct_id1: The first distinct_id to merge.
        :param str distinct_id2: The second (other) distinct_id to merge.
        :param dict meta: overrides Mixpanel special properties
        :param str api_secret: (DEPRECATED) Your Mixpanel project's API secret.

        .. deprecated::
            Both *api_key* and *api_secret* parameters are deprecated. Use
            :class:`~.ServiceAccountCredentials` with the *credentials* parameter
            instead for enhanced security. Legacy authentication will continue to work
            for backward compatibility but will be removed in a future major version.

        .. versionadded:: 4.8.0
            The *api_secret* parameter.

        .. note::
            **Recommended**: Use ServiceAccountCredentials for authentication:

            .. code-block:: python

                credentials = ServiceAccountCredentials(
                    username='YOUR_SERVICE_ACCOUNT_USERNAME',
                    secret='YOUR_SERVICE_ACCOUNT_SECRET',
                    project_id='YOUR_PROJECT_ID'
                )
                mp = Mixpanel(YOUR_TOKEN, credentials=credentials)
                # api_key still required but not used when credentials are provided
                mp.merge(
                    api_key=None,
                    distinct_id1='user123',
                    distinct_id2='user456'
                )

        See our online documentation for `more
        details
        <https://developer.mixpanel.com/reference/identities#identity-merge>`__.

        :raises UnsupportedOperationError: on a hierarchical groups client
        """
        if self._hierarchical_groups:
            msg = (
                "merge is not supported for hierarchical groups projects, which "
                "identify a user by company and user id."
            )
            raise UnsupportedOperationError(msg)
        if api_secret is not None:
            logger.warning(
                "api_secret is deprecated and will be removed in a future version. "
                "Please migrate to ServiceAccountCredentials for enhanced security."
            )
        if api_key is not None:
            logger.warning(
                "api_key is deprecated and will be removed in a future version. "
                "Please migrate to ServiceAccountCredentials for enhanced security."
            )

        event = {
            "event": "$merge",
            "properties": {
                "$distinct_ids": [distinct_id1, distinct_id2],
                "token": self._token,
            },
        }
        if meta:
            event.update(meta)

        self._consumer.send(
            "imports", json_dumps(event, cls=self._serializer), (api_key, api_secret)
        )

    def people_set(self, distinct_id, properties, meta=None):
        """Set properties of a people record.

        :param distinct_id: the profile to update; see :meth:`people_set` for
            passing a :class:`~.MixpanelIdentity`
        :type distinct_id: str or MixpanelIdentity
        :param dict properties: properties to set
        :param dict meta: overrides Mixpanel special properties

        A distinct id, or a :class:`~.MixpanelIdentity` with a
        ``distinct_id``, updates that profile through ``/engage``. On a
        hierarchical groups client, nothing is sent to ``/engage``: an
        identity with a user id and no distinct id updates the ``$user_id``
        group profile within the identity's company (or the ``$company_id``
        in ``meta``) through ``/groups``, and so does a distinct id of the
        form ``$company:{company}|$user:{user}``, which is parsed into that
        company and user. Any other distinct id raises ``ValueError``. The
        same applies to
        ``people_set_once``, ``people_unset``, ``people_union``,
        ``people_remove`` and ``people_delete``.

        If the profile does not exist, creates a new profile with these properties.

        :raises ValueError: if a :class:`~.MixpanelIdentity` or distinct id
            cannot identify a profile on this project
        :raises CompanyRequiredError: if an identity names a user but no
            company is known
        """
        return self._profile_update(distinct_id, "$set", properties, meta or {})

    def people_set_once(self, distinct_id, properties, meta=None):
        """Set properties of a people record if they are not already set.

        :param str distinct_id: the profile to update
        :param dict properties: properties to set

        Any properties that already exist on the profile will not be
        overwritten. If the profile does not exist, creates a new profile with
        these properties.
        """
        return self._profile_update(distinct_id, "$set_once", properties, meta or {})

    def people_increment(self, distinct_id, properties, meta=None):
        """Increment/decrement numerical properties of a people record.

        :param str distinct_id: the profile to update
        :param dict properties: properties to increment/decrement; values
            should be numeric

        Adds numerical values to properties of a people record. Nonexistent
        properties on the record default to zero. Negative values in
        ``properties`` will decrement the given property.

        :raises UnsupportedOperationError: on a hierarchical groups client
        :raises ValueError: if passed a :class:`~.MixpanelIdentity`
        """
        self._require_distinct_id(distinct_id, "$add", "people_increment")
        return self.people_update(
            {
                "$distinct_id": distinct_id,
                "$add": properties,
            },
            meta=meta or {},
        )

    def people_append(self, distinct_id, properties, meta=None):
        """Append to the list associated with a property.

        :param str distinct_id: the profile to update
        :param dict properties: properties to append

        Adds items to list-style properties of a people record. Appending to
        nonexistent properties results in a list with a single element. For
        example::

            mp.people_append('123', {'Items': 'Super Arm'})

        :raises UnsupportedOperationError: on a hierarchical groups client
        :raises ValueError: if passed a :class:`~.MixpanelIdentity`
        """
        self._require_distinct_id(distinct_id, "$append", "people_append")
        return self.people_update(
            {
                "$distinct_id": distinct_id,
                "$append": properties,
            },
            meta=meta or {},
        )

    def people_union(self, distinct_id, properties, meta=None):
        """Merge the values of a list associated with a property.

        :param str distinct_id: the profile to update
        :param dict properties: properties to merge

        Merges list values in ``properties`` with existing list-style
        properties of a people record. Duplicate values are ignored. For
        example::

            mp.people_union('123', {'Items': ['Super Arm', 'Fire Storm']})
        """
        return self._profile_update(distinct_id, "$union", properties, meta or {})

    def people_unset(self, distinct_id, properties, meta=None):
        """Permanently remove properties from a people record.

        :param str distinct_id: the profile to update
        :param list properties: property names to remove
        """
        return self._profile_update(distinct_id, "$unset", properties, meta)

    def people_remove(self, distinct_id, properties, meta=None):
        """Permanently remove a value from the list associated with a property.

        :param str distinct_id: the profile to update
        :param dict properties: properties to remove

        Removes items from list-style properties of a people record.
        For example::

            mp.people_remove('123', {'Items': 'Super Arm'})
        """
        return self._profile_update(distinct_id, "$remove", properties, meta or {})

    def people_delete(self, distinct_id, meta=None):
        """Permanently delete a people record.

        :param str distinct_id: the profile to delete
        """
        return self._profile_update(distinct_id, "$delete", "", meta or None)

    def people_track_charge(self, distinct_id, amount, properties=None, meta=None):
        """Track a charge on a people record.

        :param str distinct_id: the profile with which to associate the charge
        :param numeric amount: number of dollars charged
        :param dict properties: extra properties related to the transaction

        Record that you have charged the current user a certain amount of
        money. Charges recorded with this way will appear in the Mixpanel
        revenue report.

        :raises UnsupportedOperationError: on a hierarchical groups client
        :raises ValueError: if passed a :class:`~.MixpanelIdentity`
        """
        self._require_distinct_id(distinct_id, "$append", "people_track_charge")
        if properties is None:
            properties = {}
        properties.update({"$amount": amount})
        return self.people_append(
            distinct_id, {"$transactions": properties or {}}, meta=meta or {}
        )

    def people_clear_charges(self, distinct_id, meta=None):
        """Permanently clear all charges on a people record.

        :param str distinct_id: the profile whose charges will be cleared
        :raises UnsupportedOperationError: on a hierarchical groups client
        """
        if self._hierarchical_groups:
            msg = (
                "people_clear_charges is not supported for hierarchical groups "
                "projects, which can't people_track_charge."
            )
            raise UnsupportedOperationError(msg)
        return self.people_unset(
            distinct_id,
            ["$transactions"],
            meta=meta or {},
        )

    def people_update(self, message, meta=None):
        """Send a generic update to Mixpanel people analytics.

        :param dict message: the message to send

        Callers are responsible for formatting the update message as described
        in the `user profiles documentation`_. This method may be useful if you
        want to use very new or experimental features of people analytics, but
        please use the other ``people_*`` methods where possible.

        On a hierarchical groups client, nothing is sent to ``/engage``. The
        ``$distinct_id`` must be one Mixpanel built, of the form
        ``$company:{company}|$user:{user}``, and the message is sent to
        ``/groups`` as an update of that user's ``$user_id`` group profile
        within that company: ``$distinct_id`` is replaced by ``$group_key``,
        ``$group_id`` and ``$company_id``.

        :raises UnsupportedOperationError: on a hierarchical groups client, if
            ``message`` carries an operation other than ``$set``,
            ``$set_once``, ``$unset``, ``$union``, ``$remove`` or ``$delete``
        :raises ValueError: on a hierarchical groups client, if the
            ``$distinct_id`` is missing or not of the form
            ``$company:{company}|$user:{user}``

        .. _`user profiles documentation`: https://developer.mixpanel.com/reference/user-profiles
        """
        if self._hierarchical_groups:
            unsupported = _unsupported_operations(message, _PEOPLE_NON_OPERATION_KEYS)
            if unsupported:
                raise _unsupported_people_operation(unsupported[0])
            self._send_combined_user_update(message, meta)
            return
        record = {
            "$token": self._token,
            "$time": self._now(),
        }
        record.update(message)
        if meta:
            record.update(meta)
        self._consumer.send("people", json_dumps(record, cls=self._serializer))

    def _send_combined_user_update(self, message, meta):
        """Send a hierarchical groups people message to /groups, never /engage.

        A user profile on a hierarchical groups project is the ``$user_id``
        group profile within the user's company, so the message's combined
        ``$distinct_id`` is replaced by the same keys a
        ``MixpanelIdentity(user_id=..., company_id=...)`` update sends.
        """
        distinct_id = message.get("$distinct_id")
        if meta and "$distinct_id" in meta:
            distinct_id = meta["$distinct_id"]
        parsed = _parse_combined_distinct_id(distinct_id)
        if parsed is None:
            msg = (
                "User profile updates on hierarchical groups projects need a user "
                "and a company. Pass MixpanelIdentity(user_id=..., company_id=...) "
                "or a distinct id of the form $company:{company}|$user:{user}. "
                f"Nothing sent for distinct id {distinct_id!r}."
            )
            raise ValueError(msg)
        company_id, user_id = parsed
        group_message = {"$group_key": "$user_id", "$group_id": user_id}
        group_message.update(
            (key, value) for key, value in message.items() if key != "$distinct_id"
        )
        if meta:
            meta = {key: value for key, value in meta.items() if key != "$distinct_id"}
        self._send_group_update(group_message, meta, company_id)

    def _require_distinct_id(self, distinct_id, operation, method):
        """Refuse a people operation that has no hierarchical groups form."""
        if self._hierarchical_groups:
            raise _unsupported_people_operation(operation)
        if isinstance(distinct_id, MixpanelIdentity):
            msg = (
                f"{method} does not accept a MixpanelIdentity. Pass a distinct id; "
                f"{operation} has no group profile equivalent."
            )
            # ValueError like the other caller errors this client raises.
            raise ValueError(msg)  # noqa: TRY004

    def _profile_update(self, distinct_id, operation, value, meta):
        """Send a people operation for a distinct id or a MixpanelIdentity."""
        if not isinstance(distinct_id, MixpanelIdentity):
            return self.people_update(
                {"$distinct_id": distinct_id, operation: value}, meta=meta
            )

        identity = distinct_id
        self._require_identity_matches_project(identity)
        if identity.distinct_id is not None:
            # On a hierarchical groups client, people_update sends a combined
            # distinct id to /groups as its company and user, and rejects any
            # other distinct id.
            return self.people_update(
                {"$distinct_id": identity.distinct_id, operation: value}, meta=meta
            )
        if not self._hierarchical_groups:
            msg = (
                f"{identity!r} cannot identify a profile on this project. User "
                "profiles are addressed by distinct id unless the project uses "
                "hierarchical groups."
            )
            raise ValueError(msg)
        if identity.user_id is None:
            if identity.company_id is None:
                msg = (
                    f"{identity!r} names no user, so it cannot identify a profile. "
                    "Device ids identify anonymous events, not profiles."
                )
                raise ValueError(msg)
            msg = (
                f"User profile updates require a user id, and {identity!r} has "
                "none. Use group_set('$company_id', company_id, properties) to "
                "update the company's profile."
            )
            raise ValueError(msg)
        # A hierarchical groups user profile is the $user_id group profile within
        # the identity's company, whatever company this client is bound to.
        return self._send_group_update(
            {"$group_key": "$user_id", "$group_id": identity.user_id, operation: value},
            meta,
            identity.company_id,
        )

    def group_set(self, group_key, group_id, properties, meta=None):
        """Set properties of a group profile.

        :param str group_key: the group key, e.g. 'company'
        :param str group_id: the group to update
        :param dict properties: properties to set
        :param dict meta: overrides Mixpanel special properties. (See also `Mixpanel.people_set`.)

        If the profile does not exist, creates a new profile with these properties.
        """
        return self.group_update(
            {
                "$group_key": group_key,
                "$group_id": group_id,
                "$set": properties,
            },
            meta=meta or {},
        )

    def group_set_once(self, group_key, group_id, properties, meta=None):
        """Set properties of a group profile if they are not already set.

        :param str group_key: the group key, e.g. 'company'
        :param str group_id: the group to update
        :param dict properties: properties to set

        Any properties that already exist on the profile will not be
        overwritten. If the profile does not exist, creates a new profile with
        these properties.
        """
        return self.group_update(
            {
                "$group_key": group_key,
                "$group_id": group_id,
                "$set_once": properties,
            },
            meta=meta or {},
        )

    def group_union(self, group_key, group_id, properties, meta=None):
        """Merge the values of a list associated with a property.

        :param str group_key: the group key, e.g. 'company'
        :param str group_id: the group to update
        :param dict properties: properties to merge

        Merges list values in ``properties`` with existing list-style
        properties of a group profile. Duplicate values are ignored. For
        example::

            mp.group_union('company', 'Acme Inc.', {'Items': ['Super Arm', 'Fire Storm']})
        """
        return self.group_update(
            {
                "$group_key": group_key,
                "$group_id": group_id,
                "$union": properties,
            },
            meta=meta or {},
        )

    def group_unset(self, group_key, group_id, properties, meta=None):
        """Permanently remove properties from a group profile.

        :param str group_key: the group key, e.g. 'company'
        :param str group_id: the group to update
        :param list properties: property names to remove
        """
        return self.group_update(
            {
                "$group_key": group_key,
                "$group_id": group_id,
                "$unset": properties,
            },
            meta=meta,
        )

    def group_remove(self, group_key, group_id, properties, meta=None):
        """Permanently remove a value from the list associated with a property.

        :param str group_key: the group key, e.g. 'company'
        :param str group_id: the group to update
        :param dict properties: properties to remove

        Removes items from list-style properties of a group profile.
        For example::

            mp.group_remove('company', 'Acme Inc.', {'Items': 'Super Arm'})
        """
        return self.group_update(
            {
                "$group_key": group_key,
                "$group_id": group_id,
                "$remove": properties,
            },
            meta=meta or {},
        )

    def group_delete(self, group_key, group_id, meta=None):
        """Permanently delete a group profile.

        :param str group_key: the group key, e.g. 'company'
        :param str group_id: the group to delete
        """
        return self.group_update(
            {
                "$group_key": group_key,
                "$group_id": group_id,
                "$delete": "",
            },
            meta=meta or None,
        )

    def _bound_company_id(self, method):
        """Return the bound company, or raise :class:`~.CompanyRequiredError`."""
        if self._company_id is None:
            msg = (
                "Company profile updates require a company. Use "
                f"for_company(company_id) to send them. Nothing sent for {method}"
            )
            raise CompanyRequiredError(msg)
        return self._company_id

    def company_set(self, properties, meta=None):
        """Set properties of the bound company's profile.

        :param dict properties: properties to set
        :param dict meta: overrides Mixpanel special properties. (See also `Mixpanel.people_set`.)
        :raises CompanyRequiredError: if no company is bound with :meth:`for_company`

        The same as :meth:`group_set` with ``('$company_id', company_id)``::

            mp.for_company('acme').company_set({'tier': 'enterprise'})
        """
        company_id = self._bound_company_id("company_set")
        return self.group_set("$company_id", company_id, properties, meta=meta)

    def company_set_once(self, properties, meta=None):
        """Set properties of the bound company's profile if they are not already set.

        :param dict properties: properties to set
        :raises CompanyRequiredError: if no company is bound with :meth:`for_company`

        The same as :meth:`group_set_once` with ``('$company_id', company_id)``.
        """
        company_id = self._bound_company_id("company_set_once")
        return self.group_set_once("$company_id", company_id, properties, meta=meta)

    def company_union(self, properties, meta=None):
        """Merge the values of a list associated with a property of the bound company.

        :param dict properties: properties to merge
        :raises CompanyRequiredError: if no company is bound with :meth:`for_company`

        The same as :meth:`group_union` with ``('$company_id', company_id)``::

            mp.for_company('acme').company_union({'Items': ['Super Arm', 'Fire Storm']})
        """
        company_id = self._bound_company_id("company_union")
        return self.group_union("$company_id", company_id, properties, meta=meta)

    def company_unset(self, properties, meta=None):
        """Permanently remove properties from the bound company's profile.

        :param list properties: property names to remove
        :raises CompanyRequiredError: if no company is bound with :meth:`for_company`

        The same as :meth:`group_unset` with ``('$company_id', company_id)``.
        """
        company_id = self._bound_company_id("company_unset")
        return self.group_unset("$company_id", company_id, properties, meta=meta)

    def company_remove(self, properties, meta=None):
        """Permanently remove a value from a list property of the bound company.

        :param dict properties: properties to remove
        :raises CompanyRequiredError: if no company is bound with :meth:`for_company`

        The same as :meth:`group_remove` with ``('$company_id', company_id)``::

            mp.for_company('acme').company_remove({'Items': 'Super Arm'})
        """
        company_id = self._bound_company_id("company_remove")
        return self.group_remove("$company_id", company_id, properties, meta=meta)

    def company_delete(self, meta=None):
        """Permanently delete the bound company's profile.

        :raises CompanyRequiredError: if no company is bound with :meth:`for_company`

        The same as :meth:`group_delete` with ``('$company_id', company_id)``.
        """
        company_id = self._bound_company_id("company_delete")
        return self.group_delete("$company_id", company_id, meta=meta)

    def group_update(self, message, meta=None):
        """Send a generic group profile update.

        :param dict message: the message to send

        Callers are responsible for formatting the update message as documented
        in the `group profiles documentation`_. This method may be useful if you
        want to use very new or experimental features, but
        please use the other ``group_*`` methods where possible.

        On a client returned by :meth:`for_company`, the bound company is sent
        as a top-level ``$company_id``.

        :raises UnsupportedOperationError: on a hierarchical groups client, if
            ``message`` carries an operation other than ``$set``,
            ``$set_once``, ``$unset``, ``$union``, ``$remove`` or ``$delete``
        :raises CompanyRequiredError: on a hierarchical groups client, if no
            company is bound with :meth:`for_company` and neither ``message``
            nor ``meta`` carries a ``$company_id``

        .. _`group profiles documentation`: https://developer.mixpanel.com/reference/group-profiles
        """
        if self._hierarchical_groups:
            unsupported = _unsupported_operations(message, _GROUP_NON_OPERATION_KEYS)
            if unsupported:
                msg = (
                    f"{unsupported[0]} is not supported for group profiles on "
                    "hierarchical groups projects. Supported operations are "
                    f"{', '.join(GROUP_OPERATIONS)}."
                )
                raise UnsupportedOperationError(msg)
        self._send_group_update(message, meta, self._company_id)

    def _send_group_update(self, message, meta, company_id):
        """Send a /groups message, adding ``company_id`` as a top-level key."""
        if (
            self._hierarchical_groups
            and company_id is None
            and "$company_id" not in message
            and not (meta and "$company_id" in meta)
        ):
            msg = (
                "Group profile updates for hierarchical groups projects require a "
                "company. Use for_company(company_id) to send them. Nothing sent for "
                f"group {message.get('$group_key')}={message.get('$group_id')}"
            )
            raise CompanyRequiredError(msg)
        record = {
            "$token": self._token,
            "$time": self._now(),
        }
        record.update(message)
        if meta:
            record.update(meta)
        # $company_id must be top-level, not inside the operation payload
        if company_id is not None:
            record["$company_id"] = company_id
        payload = json_dumps(record, cls=self._serializer)
        self._consumer.send("groups", payload)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._local_flags_provider is not None:
            self._local_flags_provider.__exit__(exc_type, exc_val, exc_tb)
        if self._remote_flags_provider is not None:
            self._remote_flags_provider.__exit__(exc_type, exc_val, exc_tb)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._local_flags_provider is not None:
            await self._local_flags_provider.__aexit__(exc_type, exc_val, exc_tb)
        if self._remote_flags_provider is not None:
            await self._remote_flags_provider.__aexit__(exc_type, exc_val, exc_tb)


def _unsupported_people_operation(operation):
    # A hierarchical groups user profile is a group profile, so it supports what
    # /groups supports. $add and $append have no equivalent there.
    msg = (
        f"{operation} is not supported for hierarchical groups projects, whose "
        "user profiles are group profiles keyed by $user_id. Supported operations "
        f"are {', '.join(GROUP_OPERATIONS)}, so people_increment, people_append "
        "and people_track_charge have no hierarchical groups equivalent."
    )
    return UnsupportedOperationError(msg)


class UnsupportedOperationError(ValueError):
    """Raised for an operation a hierarchical groups project does not support.

    Hierarchical groups user profiles are group profiles, which support only
    ``$set``, ``$set_once``, ``$unset``, ``$union``, ``$remove`` and
    ``$delete``.
    """


class CompanyRequiredError(ValueError):
    """Raised for a hierarchical groups group profile update with no company.

    Use :meth:`Mixpanel.for_company`, or pass ``$company_id`` in ``meta``.
    Also raised by the ``company_*`` methods on a client without a bound
    company.
    """


class MixpanelException(Exception):  # noqa: N818
    """Raised by consumers when unable to send messages.

    This could be caused by a network outage or interruption, or by an invalid
    endpoint passed to :meth:`.Consumer.send`.
    """


class Consumer:
    """A consumer that sends an HTTP request directly to the Mixpanel service.

    One per call to :meth:`~.send`.

    :param str events_url: override the default events API endpoint
    :param str people_url: override the default people API endpoint
    :param str import_url: override the default import API endpoint
    :param int request_timeout: connection timeout in seconds
    :param str groups_url: override the default groups API endpoint
    :param str api_host: the Mixpanel API domain where all requests should be
        issued (unless overridden by above URLs).
    :param int retry_limit: number of times to retry each retry in case of
        connection or HTTP 5xx error; 0 to fail after first attempt.
    :param int retry_backoff_factor: In case of retries, controls sleep time. e.g.,
        sleep_seconds = backoff_factor * (2 ^ (num_total_retries - 1)).
    :param bool verify_cert: whether to verify the server certificate.
    :param ServiceAccountCredentials credentials: optional service account
        credentials for authentication. Only used for /import endpoint.

    .. versionadded:: 4.6.0
        The *api_host* parameter.
    .. versionadded:: 4.8.0
        The *verify_cert* parameter.
    """

    def __init__(
        self,
        events_url=None,
        people_url=None,
        import_url=None,
        request_timeout=None,
        groups_url=None,
        api_host="api.mixpanel.com",
        retry_limit=4,
        retry_backoff_factor=0.25,
        verify_cert=True,
        credentials=None,
    ):
        # TODO: With next major version, make the above args kwarg-only, and reorder them.
        self._endpoints = {
            "events": events_url or f"https://{api_host}/track",
            "people": people_url or f"https://{api_host}/engage",
            "groups": groups_url or f"https://{api_host}/groups",
            "imports": import_url or f"https://{api_host}/import",
        }

        self._verify_cert = verify_cert
        self._request_timeout = request_timeout
        self._credentials = credentials

        # Work around renamed argument in urllib3.
        if hasattr(urllib3.util.Retry.DEFAULT, "allowed_methods"):
            methods_arg = "allowed_methods"
        else:
            methods_arg = "method_whitelist"

        retry_args = {
            "total": retry_limit,
            "backoff_factor": retry_backoff_factor,
            "status_forcelist": set(range(500, 600)),
            methods_arg: {"POST"},
        }
        adapter = requests.adapters.HTTPAdapter(
            max_retries=urllib3.Retry(**retry_args),
        )

        self._session = requests.Session()
        self._session.mount("https://", adapter)

    def send(self, endpoint, json_message, api_key=None, api_secret=None):
        """Immediately record an event or a profile update.

        :param endpoint: the Mixpanel API endpoint appropriate for the message
        :type endpoint: "events" | "people" | "groups" | "imports"
        :param str json_message: a JSON message formatted for the endpoint
        :param str api_key: your Mixpanel project's API key
        :param str api_secret: your Mixpanel project's API secret
        :raises MixpanelException: if the endpoint doesn't exist, the server is
            unreachable, or the message cannot be processed

        .. versionadded:: 4.8.0
            The *api_secret* parameter.
        """
        if endpoint not in self._endpoints:
            msg = f'No such endpoint "{endpoint}". Valid endpoints are one of {self._endpoints.keys()}'
            raise MixpanelException(msg)

        self._write_request(
            self._endpoints[endpoint], json_message, api_key, api_secret, endpoint
        )

    def _write_request(
        self, request_url, json_message, api_key=None, api_secret=None, endpoint=None
    ):
        if isinstance(api_key, tuple):
            # Backward compatibility: api_key can be a single value or a tuple (api_key, api_secret).
            # BufferedConsumer packs them into a tuple internally for storage, so unpack here.
            api_key, api_secret = api_key

        params = {
            "data": json_message,
            "verbose": 1,
            "ip": 0,
        }

        basic_auth = None
        query_params = {}

        # Service account credentials are only supported for /import endpoint
        # For other endpoints (events, people, groups), do not use credentials
        use_credentials = self._credentials and endpoint == "imports"

        if use_credentials:
            # Service account auth - do NOT include api_key in POST body
            basic_auth = self._credentials.to_http_basic_auth()
            # Service account auth requires project_id as URL query param for backend validation
            query_params["project_id"] = self._credentials.project_id
        elif api_secret is not None:
            basic_auth = HTTPBasicAuth(api_secret, "")
            # Add api_key to POST body for legacy api_secret authentication
            if api_key:
                params["api_key"] = api_key

        try:
            response = self._session.post(
                request_url,
                params=query_params,  # URL query parameters (includes project_id for service accounts)
                data=params,  # POST body data
                auth=basic_auth,
                timeout=self._request_timeout,
                verify=self._verify_cert,
            )
        except Exception as e:
            raise MixpanelException(e) from e

        try:
            response_dict = response.json()
        except ValueError:
            msg = f"Cannot interpret Mixpanel server response: {response.text}"
            raise MixpanelException(msg) from None

        if response_dict["status"] != 1:
            raise MixpanelException("Mixpanel error: {}".format(response_dict["error"]))

        return True  # <- TODO: remove return val with major release.


class BufferedConsumer:
    """A consumer that maintains per-endpoint buffers of messages and then sends them in batches.

    This can save bandwidth and reduce the total amount of
    time required to post your events to Mixpanel.

    :param int max_size: number of :meth:`~.send` calls for a given endpoint to
        buffer before flushing automatically
    :param str events_url: override the default events API endpoint
    :param str people_url: override the default people API endpoint
    :param str import_url: override the default import API endpoint
    :param int request_timeout: connection timeout in seconds
    :param str groups_url: override the default groups API endpoint
    :param str api_host: the Mixpanel API domain where all requests should be
        issued (unless overridden by above URLs).
    :param int retry_limit: number of times to retry each retry in case of
        connection or HTTP 5xx error; 0 to fail after first attempt.
    :param int retry_backoff_factor: In case of retries, controls sleep time. e.g.,
        sleep_seconds = backoff_factor * (2 ^ (num_total_retries - 1)).
    :param bool verify_cert: whether to verify the server certificate.
    :param ServiceAccountCredentials credentials: optional service account
        credentials for authentication. Only used for /import endpoint.

    .. versionadded:: 4.6.0
        The *api_host* parameter.
    .. versionadded:: 4.8.0
        The *verify_cert* parameter.

    .. note::
        Because :class:`~.BufferedConsumer` holds events, you need to call
        :meth:`~.flush` when you're sure you're done sending them—for example,
        just before your program exits. Calls to :meth:`~.flush` will send all
        remaining unsent events being held by the instance.
    """

    def __init__(
        self,
        max_size=50,
        events_url=None,
        people_url=None,
        import_url=None,
        request_timeout=None,
        groups_url=None,
        api_host="api.mixpanel.com",
        retry_limit=4,
        retry_backoff_factor=0.25,
        verify_cert=True,
        credentials=None,
    ):
        self._consumer = Consumer(
            events_url,
            people_url,
            import_url,
            request_timeout,
            groups_url,
            api_host,
            retry_limit,
            retry_backoff_factor,
            verify_cert,
            credentials,
        )
        self._buffers = {
            "events": [],
            "people": [],
            "groups": [],
            "imports": [],
        }
        self._max_size = min(50, max_size)
        self._api_key = None
        self._api_secret = None

    def send(self, endpoint, json_message, api_key=None, api_secret=None):
        """Record an event or profile update.

        Internally, adds the message to a buffer, and then flushes the buffer
        if it has reached the configured maximum size. Note that exceptions
        raised may have been caused by a message buffered by an earlier call to
        :meth:`~.send`.

        :param endpoint: the Mixpanel API endpoint appropriate for the message
        :type endpoint: "events" | "people" | "groups" | "imports"
        :param str json_message: a JSON message formatted for the endpoint
        :param str api_key: your Mixpanel project's API key
        :param str api_secret: your Mixpanel project's API secret
        :raises MixpanelException: if the endpoint doesn't exist, the server is
            unreachable, or any buffered message cannot be processed

        .. versionadded:: 4.3.2
            The *api_key* parameter.
        """
        if endpoint not in self._buffers:
            msg = f'No such endpoint "{endpoint}". Valid endpoints are one of {self._buffers.keys()}'
            raise MixpanelException(msg)

        if not isinstance(api_key, tuple):
            api_key = (api_key, api_secret)

        buf = self._buffers[endpoint]
        buf.append(json_message)
        # TODO: Don't stick these in the instance.
        self._api_key = api_key
        self._api_secret = api_secret
        if len(buf) >= self._max_size:
            self._flush_endpoint(endpoint)

    def flush(self):
        """Immediately send all buffered messages to Mixpanel.

        :raises MixpanelException: if the server is unreachable or any buffered
            message cannot be processed
        """
        for endpoint in self._buffers:
            self._flush_endpoint(endpoint)

    def _flush_endpoint(self, endpoint):
        buf = self._buffers[endpoint]

        while buf:
            batch = buf[: self._max_size]
            batch_json = "[{}]".format(",".join(batch))
            try:
                # Credentials are passed via Consumer constructor, not send()
                self._consumer.send(endpoint, batch_json, api_key=self._api_key)
            except MixpanelException as orig_e:
                mp_e = MixpanelException(orig_e)
                mp_e.message = batch_json
                mp_e.endpoint = endpoint
                raise mp_e from orig_e
            buf = buf[self._max_size :]
        self._buffers[endpoint] = buf
