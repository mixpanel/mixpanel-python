# -*- coding: utf-8 -*-
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
from __future__ import absolute_import, unicode_literals
import datetime
import json
import logging
import time
import uuid

import requests
from requests.auth import HTTPBasicAuth
import six
from six.moves import range
import urllib3

__version__ = '4.10.0'
VERSION = __version__  # TODO: remove when bumping major version.

logger = logging.getLogger(__name__)


class DatetimeSerializer(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            fmt = '%Y-%m-%dT%H:%M:%S'
            return obj.strftime(fmt)

        return json.JSONEncoder.default(self, obj)


def json_dumps(data, cls=None):
    # Separators are specified to eliminate whitespace.
    return json.dumps(data, separators=(',', ':'), cls=cls)


class Mixpanel(object):
    """Instances of Mixpanel are used for all events and profile updates.

    :param str token: your project's Mixpanel token
    :param consumer: can be used to alter the behavior of tracking (default
        :class:`~.Consumer`)
    :param json.JSONEncoder serializer: a JSONEncoder subclass used to handle
        JSON serialization (default :class:`~.DatetimeSerializer`)

    See `Built-in consumers`_ for details about the consumer interface.

    .. versionadded:: 4.2.0
        The *serializer* parameter.
    """

    def __init__(self, token, consumer=None, serializer=DatetimeSerializer):
        self._token = token
        self._consumer = consumer or Consumer()
        self._serializer = serializer

    def _now(self):
        return time.time()

    def _make_insert_id(self):
        return uuid.uuid4().hex

    def track(self, distinct_id, event_name, properties=None, meta=None):
        """Record an event.

        :param str distinct_id: identifies the user triggering the event
        :param str event_name: a name describing the event
        :param dict properties: additional data to record; keys should be
            strings, and values should be strings, numbers, or booleans
        :param dict meta: overrides Mixpanel special properties

        ``properties`` should describe the circumstances of the event, or
        aspects of the source or user associated with it. ``meta`` is used
        (rarely) to override special values sent in the event object.
        """
        all_properties = {
            'token': self._token,
            'distinct_id': distinct_id,
            'time': self._now(),
            '$insert_id': self._make_insert_id(),
            'mp_lib': 'python',
            '$lib_version': __version__,
        }
        if properties:
            all_properties.update(properties)
        event = {
            'event': event_name,
            'properties': all_properties,
        }
        if meta:
            event.update(meta)
        self._consumer.send('events', json_dumps(event, cls=self._serializer))

    def import_data(self, api_key, distinct_id, event_name, timestamp,
                    properties=None, meta=None, api_secret=None):
        """Record an event that occurred more than 5 days in the past.

        :param str api_key: (DEPRECATED) your Mixpanel project's API key
        :param str distinct_id: identifies the user triggering the event
        :param str event_name: a name describing the event
        :param int timestamp: UTC seconds since epoch
        :param dict properties: additional data to record; keys should be
            strings, and values should be strings, numbers, or booleans
        :param dict meta: overrides Mixpanel special properties
        :param str api_secret: Your Mixpanel project's API secret.

        .. Important::
            Mixpanel's ``import`` HTTP endpoint requires the project API
            secret found in your Mixpanel project's settings. The older API key is
            no longer accessible in the Mixpanel UI, but will continue to work.
            The api_key parameter will be removed in an upcoming release of
            mixpanel-python.

        .. versionadded:: 4.8.0
            The *api_secret* parameter.

        To avoid accidentally recording invalid events, the Mixpanel API's
        ``track`` endpoint disallows events that occurred too long ago. This
        method can be used to import such events. See our online documentation
        for `more details
        <https://developer.mixpanel.com/reference/events#import-events>`__.
        """

        if api_secret is None:
            logger.warning("api_key will soon be removed from mixpanel-python; please use api_secret instead.")

        all_properties = {
            'token': self._token,
            'distinct_id': distinct_id,
            'time': timestamp,
            '$insert_id': self._make_insert_id(),
            'mp_lib': 'python',
            '$lib_version': __version__,
        }
        if properties:
            all_properties.update(properties)
        event = {
            'event': event_name,
            'properties': all_properties,
        }
        if meta:
            event.update(meta)

        self._consumer.send('imports', json_dumps(event, cls=self._serializer), (api_key, api_secret))

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
        """
        event = {
            'event': '$create_alias',
            'properties': {
                'distinct_id': original,
                'alias': alias_id,
                'token': self._token,
            },
        }
        if meta:
            event.update(meta)

        sync_consumer = Consumer()
        sync_consumer.send('events', json_dumps(event, cls=self._serializer))

    def merge(self, api_key, distinct_id1, distinct_id2, meta=None, api_secret=None):
        """
        Merges the two given distinct_ids.

        :param str api_key: (DEPRECATED) Your Mixpanel project's API key.
        :param str distinct_id1: The first distinct_id to merge.
        :param str distinct_id2: The second (other) distinct_id to merge.
        :param dict meta: overrides Mixpanel special properties
        :param str api_secret: Your Mixpanel project's API secret.

        .. Important::
            Mixpanel's ``merge`` HTTP endpoint requires the project API
            secret found in your Mixpanel project's settings. The older API key is
            no longer accessible in the Mixpanel UI, but will continue to work.
            The api_key parameter will be removed in an upcoming release of
            mixpanel-python.

        .. versionadded:: 4.8.0
            The *api_secret* parameter.

        See our online documentation for `more
        details
        <https://developer.mixpanel.com/reference/identities#identity-merge>`__.
        """
        if api_secret is None:
            logger.warning("api_key will soon be removed from mixpanel-python; please use api_secret instead.")

        event = {
            'event': '$merge',
            'properties': {
                '$distinct_ids': [distinct_id1, distinct_id2],
                'token': self._token,
            },
        }
        if meta:
            event.update(meta)
        self._consumer.send('imports', json_dumps(event, cls=self._serializer), (api_key, api_secret))

    def people_set(self, distinct_id, properties, meta=None):
        """Set properties of a people record.

        :param str distinct_id: the profile to update
        :param dict properties: properties to set
        :param dict meta: overrides Mixpanel special properties

        If the profile does not exist, creates a new profile with these properties.
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$set': properties,
        }, meta=meta or {})

    def people_set_once(self, distinct_id, properties, meta=None):
        """Set properties of a people record if they are not already set.

        :param str distinct_id: the profile to update
        :param dict properties: properties to set

        Any properties that already exist on the profile will not be
        overwritten. If the profile does not exist, creates a new profile with
        these properties.
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$set_once': properties,
        }, meta=meta or {})

    def people_increment(self, distinct_id, properties, meta=None):
        """Increment/decrement numerical properties of a people record.

        :param str distinct_id: the profile to update
        :param dict properties: properties to increment/decrement; values
            should be numeric

        Adds numerical values to properties of a people record. Nonexistent
        properties on the record default to zero. Negative values in
        ``properties`` will decrement the given property.
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$add': properties,
        }, meta=meta or {})

    def people_append(self, distinct_id, properties, meta=None):
        """Append to the list associated with a property.

        :param str distinct_id: the profile to update
        :param dict properties: properties to append

        Adds items to list-style properties of a people record. Appending to
        nonexistent properties results in a list with a single element. For
        example::

            mp.people_append('123', {'Items': 'Super Arm'})
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$append': properties,
        }, meta=meta or {})

    def people_union(self, distinct_id, properties, meta=None):
        """Merge the values of a list associated with a property.

        :param str distinct_id: the profile to update
        :param dict properties: properties to merge

        Merges list values in ``properties`` with existing list-style
        properties of a people record. Duplicate values are ignored. For
        example::

            mp.people_union('123', {'Items': ['Super Arm', 'Fire Storm']})
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$union': properties,
        }, meta=meta or {})

    def people_unset(self, distinct_id, properties, meta=None):
        """Permanently remove properties from a people record.

        :param str distinct_id: the profile to update
        :param list properties: property names to remove
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$unset': properties,
        }, meta=meta)

    def people_remove(self, distinct_id, properties, meta=None):
        """Permanently remove a value from the list associated with a property.

        :param str distinct_id: the profile to update
        :param dict properties: properties to remove

        Removes items from list-style properties of a people record.
        For example::

            mp.people_remove('123', {'Items': 'Super Arm'})
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$remove': properties,
        }, meta=meta or {})

    def people_delete(self, distinct_id, meta=None):
        """Permanently delete a people record.

        :param str distinct_id: the profile to delete
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$delete': "",
        }, meta=meta or None)

    def people_track_charge(self, distinct_id, amount,
                            properties=None, meta=None):
        """Track a charge on a people record.

        :param str distinct_id: the profile with which to associate the charge
        :param numeric amount: number of dollars charged
        :param dict properties: extra properties related to the transaction

        Record that you have charged the current user a certain amount of
        money. Charges recorded with this way will appear in the Mixpanel
        revenue report.
        """
        if properties is None:
            properties = {}
        properties.update({'$amount': amount})
        return self.people_append(
            distinct_id, {'$transactions': properties or {}}, meta=meta or {}
        )

    def people_clear_charges(self, distinct_id, meta=None):
        """Permanently clear all charges on a people record.

        :param str distinct_id: the profile whose charges will be cleared
        """
        return self.people_unset(
            distinct_id, ["$transactions"], meta=meta or {},
        )

    def people_update(self, message, meta=None):
        """Send a generic update to Mixpanel people analytics.

        :param dict message: the message to send

        Callers are responsible for formatting the update message as described
        in the `user profiles documentation`_. This method may be useful if you
        want to use very new or experimental features of people analytics, but
        please use the other ``people_*`` methods where possible.

        .. _`user profiles documentation`: https://developer.mixpanel.com/reference/user-profiles
        """
        record = {
            '$token': self._token,
            '$time': self._now(),
        }
        record.update(message)
        if meta:
            record.update(meta)
        self._consumer.send('people', json_dumps(record, cls=self._serializer))

    def group_set(self, group_key, group_id, properties, meta=None):
        """Set properties of a group profile.

        :param str group_key: the group key, e.g. 'company'
        :param str group_id: the group to update
        :param dict properties: properties to set
        :param dict meta: overrides Mixpanel special properties. (See also `Mixpanel.people_set`.)

        If the profile does not exist, creates a new profile with these properties.
        """
        return self.group_update({
            '$group_key': group_key,
            '$group_id': group_id,
            '$set': properties,
        }, meta=meta or {})

    def group_set_once(self, group_key, group_id, properties, meta=None):
        """Set properties of a group profile if they are not already set.

        :param str group_key: the group key, e.g. 'company'
        :param str group_id: the group to update
        :param dict properties: properties to set

        Any properties that already exist on the profile will not be
        overwritten. If the profile does not exist, creates a new profile with
        these properties.
        """
        return self.group_update({
            '$group_key': group_key,
            '$group_id': group_id,
            '$set_once': properties,
        }, meta=meta or {})

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
        return self.group_update({
            '$group_key': group_key,
            '$group_id': group_id,
            '$union': properties,
        }, meta=meta or {})

    def group_unset(self, group_key, group_id, properties, meta=None):
        """Permanently remove properties from a group profile.

        :param str group_key: the group key, e.g. 'company'
        :param str group_id: the group to update
        :param list properties: property names to remove
        """
        return self.group_update({
            '$group_key': group_key,
            '$group_id': group_id,
            '$unset': properties,
        }, meta=meta)

    def group_remove(self, group_key, group_id, properties, meta=None):
        """Permanently remove a value from the list associated with a property.

        :param str group_key: the group key, e.g. 'company'
        :param str group_id: the group to update
        :param dict properties: properties to remove

        Removes items from list-style properties of a group profile.
        For example::

            mp.group_remove('company', 'Acme Inc.', {'Items': 'Super Arm'})
        """
        return self.group_update({
            '$group_key': group_key,
            '$group_id': group_id,
            '$remove': properties,
        }, meta=meta or {})

    def group_delete(self, group_key, group_id, meta=None):
        """Permanently delete a group profile.

        :param str group_key: the group key, e.g. 'company'
        :param str group_id: the group to delete
        """
        return self.group_update({
            '$group_key': group_key,
            '$group_id': group_id,
            '$delete': "",
        }, meta=meta or None)

    def group_update(self, message, meta=None):
        """Send a generic group profile update

        :param dict message: the message to send

        Callers are responsible for formatting the update message as documented
        in the `group profiles documentation`_. This method may be useful if you
        want to use very new or experimental features, but
        please use the other ``group_*`` methods where possible.

        .. _`group profiles documentation`: https://developer.mixpanel.com/reference/group-profiles
        """
        record = {
            '$token': self._token,
            '$time': self._now(),
        }
        record.update(message)
        if meta:
            record.update(meta)
        self._consumer.send('groups', json_dumps(record, cls=self._serializer))


class MixpanelException(Exception):
    """Raised by consumers when unable to send messages.

    This could be caused by a network outage or interruption, or by an invalid
    endpoint passed to :meth:`.Consumer.send`.
    """
    pass


class Consumer(object):
    """
    A consumer that sends an HTTP request directly to the Mixpanel service, one
    per call to :meth:`~.send`.

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

    .. versionadded:: 4.6.0
        The *api_host* parameter.
    .. versionadded:: 4.8.0
        The *verify_cert* parameter.
    """

    def __init__(self, events_url=None, people_url=None, import_url=None,
            request_timeout=None, groups_url=None, api_host="api.mixpanel.com",
            retry_limit=4, retry_backoff_factor=0.25, verify_cert=True):
        # TODO: With next major version, make the above args kwarg-only, and reorder them.
        self._endpoints = {
            'events': events_url or 'https://{}/track'.format(api_host),
            'people': people_url or 'https://{}/engage'.format(api_host),
            'groups': groups_url or 'https://{}/groups'.format(api_host),
            'imports': import_url or 'https://{}/import'.format(api_host),
        }

        self._verify_cert = verify_cert
        self._request_timeout = request_timeout

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
        self._session.mount('http', adapter)

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
            raise MixpanelException('No such endpoint "{0}". Valid endpoints are one of {1}'.format(endpoint, self._endpoints.keys()))

        self._write_request(self._endpoints[endpoint], json_message, api_key, api_secret)

    def _write_request(self, request_url, json_message, api_key=None, api_secret=None):
        if isinstance(api_key, tuple):
            # For compatibility with subclassers, allow the auth details to be
            # packed into the existing api_key param.
            api_key, api_secret = api_key

        params = {
            'data': json_message,
            'verbose': 1,
            'ip': 0,
        }
        if api_key:
            params['api_key'] = api_key

        basic_auth = None
        if api_secret is not None:
            basic_auth = HTTPBasicAuth(api_secret, '')

        try:
            response = self._session.post(
                request_url,
                headers={
                    "Accept": "text/plain",
                    "Content-Type": "application/json",
                    "Connection": "close",
                },
                data=params,
                auth=basic_auth,
                timeout=self._request_timeout,
                verify=self._verify_cert,
            )
        except Exception as e:
            six.raise_from(MixpanelException(e), e)

        try:
            response_dict = response.json()
        except ValueError:
            raise MixpanelException('Cannot interpret Mixpanel server response: {0}'.format(response.text))

        if response_dict['status'] != 1:
            raise MixpanelException('Mixpanel error: {0}'.format(response_dict['error']))

        return True  # <- TODO: remove return val with major release.


class BufferedConsumer(object):
    """
    A consumer that maintains per-endpoint buffers of messages and then sends
    them in batches. This can save bandwidth and reduce the total amount of
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
    def __init__(self, max_size=50, events_url=None, people_url=None, import_url=None,
            request_timeout=None, groups_url=None, api_host="api.mixpanel.com",
            retry_limit=4, retry_backoff_factor=0.25, verify_cert=True):
        self._consumer = Consumer(events_url, people_url, import_url, request_timeout,
            groups_url, api_host, retry_limit, retry_backoff_factor, verify_cert)
        self._buffers = {
            'events': [],
            'people': [],
            'groups': [],
            'imports': [],
        }
        self._max_size = min(50, max_size)
        self._api_key = None

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
            raise MixpanelException('No such endpoint "{0}". Valid endpoints are one of {1}'.format(endpoint, self._buffers.keys()))

        if not isinstance(api_key, tuple):
            api_key = (api_key, api_secret)

        buf = self._buffers[endpoint]
        buf.append(json_message)
        # Fixme: Don't stick these in the instance.
        self._api_key = api_key
        self._api_secret = api_secret
        if len(buf) >= self._max_size:
            self._flush_endpoint(endpoint)

    def flush(self):
        """Immediately send all buffered messages to Mixpanel.

        :raises MixpanelException: if the server is unreachable or any buffered
            message cannot be processed
        """
        for endpoint in self._buffers.keys():
            self._flush_endpoint(endpoint)

    def _flush_endpoint(self, endpoint):
        buf = self._buffers[endpoint]

        while buf:
            batch = buf[:self._max_size]
            batch_json = '[{0}]'.format(','.join(batch))
            try:
                self._consumer.send(endpoint, batch_json, api_key=self._api_key)
            except MixpanelException as orig_e:
                mp_e = MixpanelException(orig_e)
                mp_e.message = batch_json
                mp_e.endpoint = endpoint
                six.raise_from(mp_e, orig_e)
            buf = buf[self._max_size:]
        self._buffers[endpoint] = buf
