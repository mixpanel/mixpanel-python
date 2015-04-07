import base64
import cgi
import contextlib
import datetime
import json
import time
import urlparse

from mock import Mock, patch
import pytest

import mixpanel


class LogConsumer(object):

    def __init__(self):
        self.log = []

    def send(self, endpoint, event, api_key=None):
        if api_key:
            self.log.append((endpoint, json.loads(event), api_key))
        else:
            self.log.append((endpoint, json.loads(event)))


# Convert a query string with base64 data into a dict for safe comparison.
def qs(s):
    blob = cgi.parse_qs(s)
    if 'data' in blob:
        if len(blob['data']) != 1:
            pytest.fail('found multi-item data: %s' % blob['data'])
        blob['data'] = json.loads(base64.b64decode(blob['data'][0]))
    return blob


class TestMixpanel:
    TOKEN = '12345'

    def setup_method(self, method):
        self.consumer = LogConsumer()
        self.mp = mixpanel.Mixpanel('12345', consumer=self.consumer)
        self.mp._now = lambda: 1000.1

    def test_track(self):
        self.mp.track('ID', 'button press', {'size': 'big', 'color': 'blue'})
        assert self.consumer.log == [(
            'events', {
                'event': 'button press',
                'properties': {
                    'token': self.TOKEN,
                    'size': 'big',
                    'color': 'blue',
                    'distinct_id': 'ID',
                    'time': int(self.mp._now()),
                    'mp_lib': 'python',
                    '$lib_version': mixpanel.__version__,
                }
            }
        )]

    def test_import_data(self):
        timestamp = time.time()
        self.mp.import_data('MY_API_KEY', 'ID', 'button press', timestamp, {'size': 'big', 'color': 'blue'})
        assert self.consumer.log == [(
            'imports', {
                'event': 'button press',
                'properties': {
                    'token': self.TOKEN,
                    'size': 'big',
                    'color': 'blue',
                    'distinct_id': 'ID',
                    'time': int(timestamp),
                    'mp_lib': 'python',
                    '$lib_version': mixpanel.__version__,
                },
            },
            'MY_API_KEY'
        )]

    def test_track_meta(self):
        self.mp.track('ID', 'button press', {'size': 'big', 'color': 'blue'},
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
        mock_response = Mock()
        mock_response.read.return_value = '{"status":1, "error": null}'
        with patch('urllib2.urlopen', return_value=mock_response) as urlopen:
            self.mp.alias('ALIAS', 'ORIGINAL ID')
            assert self.consumer.log == []
            assert urlopen.call_count == 1
            ((request,), _) = urlopen.call_args

            assert request.get_full_url() == 'https://api.mixpanel.com/track'
            assert qs(request.get_data()) == \
                qs('ip=0&data=eyJldmVudCI6IiRjcmVhdGVfYWxpYXMiLCJwcm9wZXJ0aWVzIjp7ImFsaWFzIjoiQUxJQVMiLCJ0b2tlbiI6IjEyMzQ1IiwiZGlzdGluY3RfaWQiOiJPUklHSU5BTCBJRCJ9fQ%3D%3D&verbose=1')

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


class TestConsumer:

    @classmethod
    def setup_class(cls):
        cls.consumer = mixpanel.Consumer(request_timeout=30)

    @contextlib.contextmanager
    def _assertSends(self, expect_url, expect_data):
        mock_response = Mock()
        mock_response.read.return_value = '{"status":1, "error": null}'
        with patch('urllib2.urlopen', return_value=mock_response) as urlopen:
            yield

            assert urlopen.call_count == 1

            (call_args, kwargs) = urlopen.call_args
            (request,) = call_args
            timeout = kwargs.get('timeout', None)

            assert request.get_full_url() == expect_url
            assert qs(request.get_data()) == qs(expect_data)
            assert timeout == self.consumer._request_timeout

    def test_send_events(self):
        with self._assertSends('https://api.mixpanel.com/track', 'ip=0&data=IkV2ZW50Ig%3D%3D&verbose=1'):
            self.consumer.send('events', '"Event"')

    def test_send_people(self):
        with self._assertSends('https://api.mixpanel.com/engage', 'ip=0&data=IlBlb3BsZSI%3D&verbose=1'):
            self.consumer.send('people', '"People"')


class TestBufferedConsumer:

    @classmethod
    def setup_class(cls):
        cls.MAX_LENGTH = 10
        cls.consumer = mixpanel.BufferedConsumer(cls.MAX_LENGTH)
        cls.mock = Mock()
        cls.mock.read.return_value = '{"status":1, "error": null}'

    def test_buffer_hold_and_flush(self):
        with patch('urllib2.urlopen', return_value=self.mock) as urlopen:
            self.consumer.send('events', '"Event"')
            assert not self.mock.called
            self.consumer.flush()

            assert urlopen.call_count == 1

            (call_args, kwargs) = urlopen.call_args
            (request,) = call_args
            timeout = kwargs.get('timeout', None)

            assert request.get_full_url() == 'https://api.mixpanel.com/track'
            assert qs(request.get_data()) == qs('ip=0&data=WyJFdmVudCJd&verbose=1')
            assert timeout is None

    def test_buffer_fills_up(self):
        with patch('urllib2.urlopen', return_value=self.mock) as urlopen:
            for i in xrange(self.MAX_LENGTH - 1):
                self.consumer.send('events', '"Event"')
                assert not self.mock.called

            self.consumer.send('events', '"Last Event"')

            assert urlopen.call_count == 1
            ((request,), _) = urlopen.call_args
            assert request.get_full_url() == 'https://api.mixpanel.com/track'
            assert qs(request.get_data()) == \
                qs('ip=0&data=WyJFdmVudCIsIkV2ZW50IiwiRXZlbnQiLCJFdmVudCIsIkV2ZW50IiwiRXZlbnQiLCJFdmVudCIsIkV2ZW50IiwiRXZlbnQiLCJMYXN0IEV2ZW50Il0%3D&verbose=1')


class TestFunctional:

    @classmethod
    def setup_class(cls):
        cls.TOKEN = '12345'
        cls.mp = mixpanel.Mixpanel(cls.TOKEN)
        cls.mp._now = lambda: 1000

    @contextlib.contextmanager
    def _assertRequested(self, expect_url, expect_data):
        mock_response = Mock()
        mock_response.read.return_value = '{"status":1, "error": null}'
        with patch('urllib2.urlopen', return_value=mock_response) as urlopen:
            yield

            assert urlopen.call_count == 1
            ((request,), _) = urlopen.call_args
            assert request.get_full_url() == expect_url
            data = urlparse.parse_qs(request.get_data())
            assert len(data['data']) == 1
            payload_encoded = data['data'][0]
            payload_json = base64.b64decode(payload_encoded)
            payload = json.loads(payload_json)
            assert payload == expect_data

    def test_track_functional(self):
        expect_data = {u'event': {u'color': u'blue', u'size': u'big'}, u'properties': {u'mp_lib': u'python', u'token': u'12345', u'distinct_id': u'button press', u'$lib_version': unicode(mixpanel.__version__), u'time': 1000}}
        with self._assertRequested('https://api.mixpanel.com/track', expect_data):
            self.mp.track('button press', {'size': 'big', 'color': 'blue'})

    def test_people_set_functional(self):
        expect_data = {u'$distinct_id': u'amq', u'$set': {u'birth month': u'october', u'favorite color': u'purple'}, u'$time': 1000000, u'$token': u'12345'}
        with self._assertRequested('https://api.mixpanel.com/engage', expect_data):
            self.mp.people_set('amq', {'birth month': 'october', 'favorite color': 'purple'})
