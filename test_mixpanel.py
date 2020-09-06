from __future__ import absolute_import, unicode_literals
import base64
import contextlib
import datetime
import decimal
import json
import time

from mock import Mock, patch
import pytest
import six
import urllib3
from six.moves import range

import mixpanel


class LogConsumer(object):

    def __init__(self):
        self.log = []

    def send(self, endpoint, event, api_key=None):
        if api_key:
            self.log.append((endpoint, json.loads(event), api_key))
        else:
            self.log.append((endpoint, json.loads(event)))


class TestMixpanel:
    TOKEN = '12345'

    def setup_method(self, method):
        self.consumer = LogConsumer()
        self.mp = mixpanel.Mixpanel('12345', consumer=self.consumer)
        self.mp._now = lambda: 1000.1

    def test_track(self):
        self.mp.track('ID', 'button press', {'size': 'big', 'color': 'blue', '$insert_id': 'abc123'})
        assert self.consumer.log == [(
            'events', {
                'event': 'button press',
                'properties': {
                    'token': self.TOKEN,
                    'size': 'big',
                    'color': 'blue',
                    'distinct_id': 'ID',
                    'time': int(self.mp._now()),
                    '$insert_id': 'abc123',
                    'mp_lib': 'python',
                    '$lib_version': mixpanel.__version__,
                }
            }
        )]

    def test_import_data(self):
        timestamp = time.time()
        self.mp.import_data('MY_API_KEY', 'ID', 'button press', timestamp, {'size': 'big', 'color': 'blue', '$insert_id': 'abc123'})
        assert self.consumer.log == [(
            'imports', {
                'event': 'button press',
                'properties': {
                    'token': self.TOKEN,
                    'size': 'big',
                    'color': 'blue',
                    'distinct_id': 'ID',
                    'time': int(timestamp),
                    '$insert_id': 'abc123',
                    'mp_lib': 'python',
                    '$lib_version': mixpanel.__version__,
                },
            },
            'MY_API_KEY'
        )]

    def test_track_meta(self):
        self.mp.track('ID', 'button press', {'size': 'big', 'color': 'blue', '$insert_id': 'abc123'},
                      meta={'ip': 0})
        assert self.consumer.log == [(
            'events', {
                'event': 'button press',
                'properties': {
                    'token': self.TOKEN,
                    'size': 'big',
                    'color': 'blue',
                    'distinct_id': 'ID',
                    'time': int(self.mp._now()),
                    '$insert_id': 'abc123',
                    'mp_lib': 'python',
                    '$lib_version': mixpanel.__version__,
                },
                'ip': 0,
            }
        )]

    def test_people_set(self):
        self.mp.people_set('amq', {'birth month': 'october', 'favorite color': 'purple'})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$set': {
                    'birth month': 'october',
                    'favorite color': 'purple',
                },
            }
        )]

    def test_people_set_once(self):
        self.mp.people_set_once('amq', {'birth month': 'october', 'favorite color': 'purple'})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$set_once': {
                    'birth month': 'october',
                    'favorite color': 'purple',
                },
            }
        )]

    def test_people_increment(self):
        self.mp.people_increment('amq', {'Albums Released': 1})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$add': {
                    'Albums Released': 1,
                },
            }
        )]

    def test_people_append(self):
        self.mp.people_append('amq', {'birth month': 'october', 'favorite color': 'purple'})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$append': {
                    'birth month': 'october',
                    'favorite color': 'purple',
                },
            }
        )]

    def test_people_union(self):
        self.mp.people_union('amq', {'Albums': ['Diamond Dogs']})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$union': {
                    'Albums': ['Diamond Dogs'],
                },
            }
        )]

    def test_people_unset(self):
        self.mp.people_unset('amq', ['Albums', 'Singles'])
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$unset': ['Albums', 'Singles'],
            }
        )]

    def test_people_remove(self):
        self.mp.people_remove('amq', {'Albums': 'Diamond Dogs'})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$remove': {'Albums': 'Diamond Dogs'},
            }
        )]

    def test_people_track_charge(self):
        self.mp.people_track_charge('amq', 12.65, {'$time': '2013-04-01T09:02:00'})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$append': {
                    '$transactions': {
                        '$time': '2013-04-01T09:02:00',
                        '$amount': 12.65,
                    },
                },
            }
        )]

    def test_people_track_charge_without_properties(self):
        self.mp.people_track_charge('amq', 12.65)
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$append': {
                    '$transactions': {
                        '$amount': 12.65,
                    },
                },
            }
        )]

    def test_people_clear_charges(self):
        self.mp.people_clear_charges('amq')
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$unset': ['$transactions'],
            }
        )]

    def test_people_set_created_date_string(self):
        created = '2014-02-14T01:02:03'
        self.mp.people_set('amq', {'$created': created, 'favorite color': 'purple'})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$set': {
                    '$created': created,
                    'favorite color': 'purple',
                },
            }
        )]

    def test_people_set_created_date_datetime(self):
        created = datetime.datetime(2014, 2, 14, 1, 2, 3)
        self.mp.people_set('amq', {'$created': created, 'favorite color': 'purple'})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$set': {
                    '$created': '2014-02-14T01:02:03',
                    'favorite color': 'purple',
                },
            }
        )]

    def test_alias(self):
        # More complicated since alias() forces a synchronous call.
        mock_response = Mock()
        mock_response.data = six.b('{"status": 1, "error": null}')
        with patch('mixpanel.urllib3.PoolManager.request', return_value=mock_response) as req:
            self.mp.alias('ALIAS', 'ORIGINAL ID')
            assert self.consumer.log == []
            assert req.call_count == 1
            ((method, url), kwargs) = req.call_args

            assert method == 'POST'
            assert url == 'https://api.mixpanel.com/track'
            expected_data = {"event":"$create_alias","properties":{"alias":"ALIAS","token":"12345","distinct_id":"ORIGINAL ID"}}
            assert json.loads(kwargs["fields"]["data"]) == expected_data

    def test_merge(self):
        self.mp.merge('my_good_api_key', 'd1', 'd2')

        assert self.consumer.log == [(
            'imports',
            {
                'event': '$merge',
                'properties': {
                    '$distinct_ids': ['d1', 'd2'],
                    'token': self.TOKEN,
                }
            },
            'my_good_api_key',
        )]

    def test_people_meta(self):
        self.mp.people_set('amq', {'birth month': 'october', 'favorite color': 'purple'},
                           meta={'$ip': 0, '$ignore_time': True})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$set': {
                    'birth month': 'october',
                    'favorite color': 'purple',
                },
                '$ip': 0,
                '$ignore_time': True,
            }
        )]

    def test_group_set(self):
        self.mp.group_set('company', 'amq', {'birth month': 'october', 'favorite color': 'purple'})
        assert self.consumer.log == [(
            'groups', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$group_key': 'company',
                '$group_id': 'amq',
                '$set': {
                    'birth month': 'october',
                    'favorite color': 'purple',
                },
            }
        )]

    def test_group_set_once(self):
        self.mp.group_set_once('company', 'amq', {'birth month': 'october', 'favorite color': 'purple'})
        assert self.consumer.log == [(
            'groups', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$group_key': 'company',
                '$group_id': 'amq',
                '$set_once': {
                    'birth month': 'october',
                    'favorite color': 'purple',
                },
            }
        )]

    def test_group_union(self):
        self.mp.group_union('company', 'amq', {'Albums': ['Diamond Dogs']})
        assert self.consumer.log == [(
            'groups', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$group_key': 'company',
                '$group_id': 'amq',
                '$union': {
                    'Albums': ['Diamond Dogs'],
                },
            }
        )]

    def test_group_unset(self):
        self.mp.group_unset('company', 'amq', ['Albums', 'Singles'])
        assert self.consumer.log == [(
            'groups', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$group_key': 'company',
                '$group_id': 'amq',
                '$unset': ['Albums', 'Singles'],
            }
        )]

    def test_group_remove(self):
        self.mp.group_remove('company', 'amq', {'Albums': 'Diamond Dogs'})
        assert self.consumer.log == [(
            'groups', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$group_key': 'company',
                '$group_id': 'amq',
                '$remove': {'Albums': 'Diamond Dogs'},
            }
        )]

    def test_custom_json_serializer(self):
        decimal_string = '12.05'
        with pytest.raises(TypeError) as excinfo:
            self.mp.track('ID', 'button press', {'size': decimal.Decimal(decimal_string)})
        assert "not JSON serializable" in str(excinfo.value)

        class CustomSerializer(mixpanel.DatetimeSerializer):
            def default(self, obj):
                if isinstance(obj, decimal.Decimal):
                    return obj.to_eng_string()

        self.mp._serializer = CustomSerializer
        self.mp.track('ID', 'button press', {'size': decimal.Decimal(decimal_string), '$insert_id': 'abc123'})
        assert self.consumer.log == [(
            'events', {
                'event': 'button press',
                'properties': {
                    'token': self.TOKEN,
                    'size': decimal_string,
                    'distinct_id': 'ID',
                    'time': int(self.mp._now()),
                    '$insert_id': 'abc123',
                    'mp_lib': 'python',
                    '$lib_version': mixpanel.__version__,
                }
            }
        )]


class TestConsumer:
    @classmethod
    def setup_class(cls):
        cls.consumer = mixpanel.Consumer(request_timeout=30)

    @contextlib.contextmanager
    def _assertSends(self, expect_url, expect_data, consumer=None):
        if consumer is None:
            consumer = self.consumer

        mock_response = Mock()
        mock_response.data = six.b('{"status": 1, "error": null}')
        with patch('mixpanel.urllib3.PoolManager.request', return_value=mock_response) as req:
            yield

            assert req.call_count == 1
            (call_args, kwargs) = req.call_args
            (method, url) = call_args
            assert method == 'POST'
            assert url == expect_url
            assert kwargs["fields"] == expect_data
            # FIXME
            # timeout = kwargs.get('timeout', None)
            # assert timeout == self.consumer._request_timeout

    def test_send_events(self):
        with self._assertSends('https://api.mixpanel.com/track', {"ip": 0, "verbose": 1, "data": '{"foo":"bar"}'}):
            self.consumer.send('events', '{"foo":"bar"}')

    def test_send_people(self):
        with self._assertSends('https://api.mixpanel.com/engage', {"ip": 0, "verbose": 1, "data": '{"foo":"bar"}'}):
            self.consumer.send('people', '{"foo":"bar"}')

    def test_consumer_override_api_host(self):
        consumer = mixpanel.Consumer(api_host="api-eu.mixpanel.com")
        with self._assertSends('https://api-eu.mixpanel.com/track', {"ip": 0, "verbose": 1, "data": '{"foo":"bar"}'}, consumer=consumer):
            consumer.send('events', '{"foo":"bar"}')
        with self._assertSends('https://api-eu.mixpanel.com/engage', {"ip": 0, "verbose": 1, "data": '{"foo":"bar"}'}, consumer=consumer):
            consumer.send('people', '{"foo":"bar"}')

    def test_unknown_endpoint(self):
        with pytest.raises(mixpanel.MixpanelException):
            self.consumer.send('unknown', '1')


class TestBufferedConsumer:

    @classmethod
    def setup_class(cls):
        cls.MAX_LENGTH = 10
        cls.consumer = mixpanel.BufferedConsumer(cls.MAX_LENGTH)
        cls.consumer._consumer = LogConsumer()
        cls.log = cls.consumer._consumer.log

    def setup_method(self):
        del self.log[:]

    def test_buffer_hold_and_flush(self):
        self.consumer.send('events', '"Event"')
        assert len(self.log) == 0
        self.consumer.flush()
        assert self.log == [('events', ['Event'])]

    def test_buffer_fills_up(self):
        for i in range(self.MAX_LENGTH - 1):
            self.consumer.send('events', '"Event"')
        assert len(self.log) == 0

        self.consumer.send('events', '"Last Event"')
        assert len(self.log) == 1
        assert self.log == [('events', [
            'Event', 'Event', 'Event', 'Event', 'Event',
            'Event', 'Event', 'Event', 'Event', 'Last Event',
        ])]

    def test_unknown_endpoint_raises_on_send(self):
        # Ensure the exception isn't hidden until a flush.
        with pytest.raises(mixpanel.MixpanelException):
            self.consumer.send('unknown', '1')

    def test_useful_reraise_in_flush_endpoint(self):
        error_mock = Mock()
        error_mock.data = six.b('{"status": 0, "error": "arbitrary error"}')
        broken_json = '{broken JSON'
        consumer = mixpanel.BufferedConsumer(2)
        with patch('mixpanel.urllib3.PoolManager.request', return_value=error_mock):
            consumer.send('events', broken_json)
            with pytest.raises(mixpanel.MixpanelException) as excinfo:
                consumer.flush()
            assert excinfo.value.message == '[%s]' % broken_json
            assert excinfo.value.endpoint == 'events'

    def test_send_remembers_api_key(self):
        self.consumer.send('imports', '"Event"', api_key='MY_API_KEY')
        assert len(self.log) == 0
        self.consumer.flush()
        assert self.log == [('imports', ['Event'], 'MY_API_KEY')]


class TestFunctional:
    @classmethod
    def setup_class(cls):
        cls.TOKEN = '12345'
        cls.mp = mixpanel.Mixpanel(cls.TOKEN)
        cls.mp._now = lambda: 1000

    @contextlib.contextmanager
    def _assertRequested(self, expect_url, expect_data):
        res = Mock()
        res.data = six.b('{"status": 1, "error": null}')
        with patch('mixpanel.urllib3.PoolManager.request', return_value=res) as req:
            yield

            assert req.call_count == 1
            ((method, url,), data) = req.call_args
            data = data["fields"]["data"]
            assert method == 'POST'
            assert url == expect_url
            payload = json.loads(data)
            assert payload == expect_data

    def test_track_functional(self):
        expect_data = {'event': 'button_press', 'properties': {'size': 'big', 'color': 'blue', 'mp_lib': 'python', 'token': '12345', 'distinct_id': 'player1', '$lib_version': mixpanel.__version__, 'time': 1000, '$insert_id': 'xyz1200'}}
        with self._assertRequested('https://api.mixpanel.com/track', expect_data):
            self.mp.track('player1', 'button_press', {'size': 'big', 'color': 'blue', '$insert_id': 'xyz1200'})

    def test_people_set_functional(self):
        expect_data = {'$distinct_id': 'amq', '$set': {'birth month': 'october', 'favorite color': 'purple'}, '$time': 1000000, '$token': '12345'}
        with self._assertRequested('https://api.mixpanel.com/engage', expect_data):
            self.mp.people_set('amq', {'birth month': 'october', 'favorite color': 'purple'})
