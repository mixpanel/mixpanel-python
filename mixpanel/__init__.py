# -*- coding: utf-8 -*-
"""This is the official Mixpanel client library for Python.

Mixpanel client libraries allow for tracking events and setting properties on
People Analytics profiles from your server-side projects. This is the API
documentation; you may also be interested in the higher-level `usage
documentation`_. If your users are interacting with your application via the
web, you may also be interested in our `JavaScript library`_.

.. _`Javascript library`: https://mixpanel.com/help/reference/javascript
.. _`usage documentation`: https://mixpanel.com/help/reference/python

:class:`~.Mixpanel` is the primary class for tracking events and sending People
Analytics updates. :class:`~.Consumer` and :class:`~.BufferedConsumer` allow
callers to customize the IO characteristics of their tracking.
"""
from __future__ import absolute_import, unicode_literals
import base64
import datetime
import json
import time

import six
from six.moves import urllib

__version__ = '4.1.0'
VERSION = __version__  # TODO: remove when bumping major version.


class DatetimeSerializer(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            fmt = '%Y-%m-%dT%H:%M:%S'
            return obj.strftime(fmt)

        return json.JSONEncoder.default(self, obj)


class Mixpanel(object):
    """Instances of Mixpanel are used for all events and profile updates.

    :param str token: your project's Mixpanel token
    :param consumer: can be used to alter the behavior of tracking (default
        :class:`~.Consumer`)
    :param serlializer: can be used to specify your own JSON serlializer (default
        :class:`~.DatetimeSerializer`)

    See `Built-in consumers`_ for details about the consumer interface.
    """

    def __init__(self, token, consumer=None, serializer=None):
        self._token = token
        self._consumer = consumer or Consumer()
        self._serializer = serializer or DatetimeSerializer

    def _now(self):
        return time.time()

    def _json_dumps(self, data):
        # Separators are specified to eliminate whitespace.
        return json.dumps(data, separators=(',', ':'), cls=self._serializer)

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
            'time': int(self._now()),
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
        self._consumer.send('events', self._json_dumps(event))

    def import_data(self, api_key, distinct_id, event_name, timestamp,
                    properties=None, meta=None):
        """Record an event that occured more than 5 days in the past.

        :param str api_key: your Mixpanel project's API key
        :param str distinct_id: identifies the user triggering the event
        :param str event_name: a name describing the event
        :param int timestamp: UTC seconds since epoch
        :param dict properties: additional data to record; keys should be
            strings, and values should be strings, numbers, or booleans
        :param dict meta: overrides Mixpanel special properties

        To avoid accidentally recording invalid events, the Mixpanel API's
        ``track`` endpoint disallows events that occurred too long ago. This
        method can be used to import such events. See our online documentation
        for `more details
        <https://mixpanel.com/docs/api-documentation/importing-events-older-than-31-days>`__.
        """
        all_properties = {
            'token': self._token,
            'distinct_id': distinct_id,
            'time': int(timestamp),
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
        self._consumer.send('imports', self._json_dumps(event), api_key)

    def alias(self, alias_id, original, meta=None):
        """Apply a custom alias to a people record.

        :param str alias_id: the new distinct_id
        :param str original: the previous distinct_id
        :param dict meta: overrides Mixpanel special properties

        Immediately creates a one-way mapping between two ``distinct_ids``.
        Events triggered by the new id will be associated with the existing
        user's profile and behavior. See our online documentation for `more
        details
        <https://mixpanel.com/docs/integration-libraries/using-mixpanel-alias>`__.

        .. note::
            Calling this method *always* results in a synchronous HTTP request
            to Mixpanel servers, regardless of any custom consumer.
        """
        sync_consumer = Consumer()
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
        sync_consumer.send('events', self._json_dumps(event))

    def people_set(self, distinct_id, properties, meta=None):
        """Set properties of a people record.

        :param str distinct_id: the profile to update
        :param dict properties: properties to set
        :param dict meta: overrides Mixpanel `special properties`_

        .. _`special properties`: https://mixpanel.com/help/reference/http#people-analytics-updates

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

        Callers are responsible for formatting the update message as documented
        in the `Mixpanel HTTP specification`_. This method may be useful if you
        want to use very new or experimental features of people analytics, but
        please use the other ``people_*`` methods where possible.

        .. _`Mixpanel HTTP specification`: https://mixpanel.com/help/reference/http
        """
        record = {
            '$token': self._token,
            '$time': int(self._now() * 1000),
        }
        record.update(message)
        if meta:
            record.update(meta)
        self._consumer.send('people', self._json_dumps(record))


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
    """

    def __init__(self, events_url=None, people_url=None, import_url=None, request_timeout=None):
        self._endpoints = {
            'events': events_url or 'https://api.mixpanel.com/track',
            'people': people_url or 'https://api.mixpanel.com/engage',
            'imports': import_url or 'https://api.mixpanel.com/import',
        }
        self._request_timeout = request_timeout

    def send(self, endpoint, json_message, api_key=None):
        """Immediately record an event or a profile update.

        :param endpoint: the Mixpanel API endpoint appropriate for the message
        :type endpoint: "events" | "people" | "imports"
        :param str json_message: a JSON message formatted for the endpoint
        :raises MixpanelException: if the endpoint doesn't exist, the server is
            unreachable, or the message cannot be processed
        """
        if endpoint in self._endpoints:
            self._write_request(self._endpoints[endpoint], json_message, api_key)
        else:
            raise MixpanelException('No such endpoint "{0}". Valid endpoints are one of {1}'.format(endpoint, self._endpoints.keys()))

    def _write_request(self, request_url, json_message, api_key=None):
        data = {
            'data': base64.b64encode(json_message.encode('utf8')),
            'verbose': 1,
            'ip': 0,
        }
        if api_key:
            data.update({'api_key': api_key})
        encoded_data = urllib.parse.urlencode(data).encode('utf8')
        try:
            request = urllib.request.Request(request_url, encoded_data)

            # Note: We don't send timeout=None here, because the timeout in urllib2 defaults to
            # an internal socket timeout, not None.
            if self._request_timeout is not None:
                response = urllib.request.urlopen(request, timeout=self._request_timeout).read()
            else:
                response = urllib.request.urlopen(request).read()
        except urllib.error.HTTPError as e:
            raise six.raise_from(MixpanelException(e), e)

        try:
            response = json.loads(response.decode('utf8'))
        except ValueError:
            raise MixpanelException('Cannot interpret Mixpanel server response: {0}'.format(response))

        if response['status'] != 1:
            raise MixpanelException('Mixpanel error: {0}'.format(response['error']))

        return True


class BufferedConsumer(object):
    """
    A consumer that maintains per-endpoint buffers of messages and then sends
    them in batches. This can save bandwidth and reduce the total amount of
    time required to post your events to Mixpanel.

    .. note::
        Because :class:`~.BufferedConsumer` holds events, you need to call
        :meth:`~.flush` when you're sure you're done sending them—for example,
        just before your program exits. Calls to :meth:`~.flush` will send all
        remaining unsent events being held by the instance.

    :param int max_size: number of :meth:`~.send` calls for a given endpoint to
        buffer before flushing automatically
    :param str events_url: override the default events API endpoint
    :param str people_url: override the default people API endpoint
    :param str import_url: override the default import API endpoint
    :param int request_timeout: connection timeout in seconds
    """
    def __init__(self, max_size=50, events_url=None, people_url=None, import_url=None, request_timeout=None):
        self._consumer = Consumer(events_url, people_url, import_url, request_timeout)
        self._buffers = {
            'events': [],
            'people': [],
            'imports': [],
        }
        self._max_size = min(50, max_size)

    def send(self, endpoint, json_message):
        """Record an event or profile update.

        Internally, adds the message to a buffer, and then flushes the buffer
        if it has reached the configured maximum size. Note that exceptions
        raised may have been caused by a message buffered by an earlier call to
        :meth:`~.send`.

        :param endpoint: the Mixpanel API endpoint appropriate for the message
        :type endpoint: "events" | "people" | "imports"
        :param str json_message: a JSON message formatted for the endpoint
        :raises MixpanelException: if the endpoint doesn't exist, the server is
            unreachable, or any buffered message cannot be processed
        """
        if endpoint not in self._buffers:
            raise MixpanelException('No such endpoint "{0}". Valid endpoints are one of {1}'.format(endpoint, self._buffers.keys()))

        buf = self._buffers[endpoint]
        buf.append(json_message)
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
                self._consumer.send(endpoint, batch_json)
            except MixpanelException as orig_e:
                mp_e = MixpanelException(orig_e)
                mp_e.message = batch_json
                mp_e.endpoint = endpoint
                raise six.raise_from(mp_e, orig_e)
            buf = buf[self._max_size:]
        self._buffers[endpoint] = buf
