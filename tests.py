#!/usr/bin/env python3.3
import base64
import contextlib
import json
import unittest
import urllib
from unittest.mock import MagicMock, patch

import mixpanel

class LogConsumer(object):
    def __init__(self):
        self.log = []

    def send(self, endpoint, event):
        self.log.append((endpoint, json.loads(event)))

class MixpanelTestCase(unittest.TestCase):
    def setUp(self):
        self.TOKEN = '12345'
        self.consumer = LogConsumer()
        self.mp = mixpanel.Mixpanel('12345', consumer=self.consumer)
        self.mp._now = lambda : 1000.1

    def test_track(self):
        self.mp.track('ID', 'button press', {'size': 'big', 'color': 'blue'})
        self.assertEqual(self.consumer.log, [(
            'events', {
                'event': 'button press',
                'properties': {
                    'token': self.TOKEN,
                    'size': 'big',
                    'color': 'blue',
                    'distinct_id': 'ID',
                    'time': int(self.mp._now()),
                    'mp_lib': 'python',
                    '$lib_version': mixpanel.VERSION,
                }
            }
        )])

    def test_track_meta(self):
        self.mp.track('ID', 'button press', {'size': 'big', 'color': 'blue'},
            meta={'$ip': 0, '$ignore_time': True,})
        self.assertEqual(self.consumer.log, [(
            'events', {
                'event': 'button press',
                'properties': {
                    'token': self.TOKEN,
                    'size': 'big',
                    'color': 'blue',
                    'distinct_id': 'ID',
                    'time': int(self.mp._now()),
                    'mp_lib': 'python',
                    '$lib_version': mixpanel.VERSION,
                },
                '$ip': 0,
                '$ignore_time': True,
            }
        )])

    def test_people_set(self):
        self.mp.people_set('amq', {'birth month': 'october', 'favorite color': 'purple'})
        self.assertEqual(self.consumer.log, [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$set': {
                    'birth month': 'october',
                    'favorite color': 'purple',
                },
            }
        )])

    def test_people_set_once(self):
        self.mp.people_set_once('amq', {'birth month': 'october', 'favorite color': 'purple'})
        self.assertEqual(self.consumer.log, [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$set_once': {
                    'birth month': 'october',
                    'favorite color': 'purple',
                },
            }
        )])

    def test_people_increment(self):
        self.mp.people_increment('amq', {'Albums Released': 1})
        self.assertEqual(self.consumer.log, [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$add': {
                    'Albums Released': 1,
                },
            }
        )])

    def test_people_append(self):
        self.mp.people_append('amq', {'birth month': 'october', 'favorite color': 'purple'})
        self.assertEqual(self.consumer.log, [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$append': {
                    'birth month': 'october',
                    'favorite color': 'purple',
                },
            }
        )])

    def test_people_union(self):
        self.mp.people_union('amq', {'Albums': [ 'Diamond Dogs'] })
        self.assertEqual(self.consumer.log, [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$union': {
                    'Albums': [ 'Diamond Dogs' ],
                },
            }
        )])

    def test_people_unset(self):
        self.mp.people_unset('amq', [ 'Albums', 'Singles' ])
        self.assertEqual(self.consumer.log, [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$unset': [ 'Albums', 'Singles' ],
            }
        )])

    def test_people_track_charge(self):
        self.mp.people_track_charge('amq', 12.65, { '$time': '2013-04-01T09:02:00' })
        self.assertEqual(self.consumer.log, [(
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
        )])

    def test_people_clear_charges(self):
        self.mp.people_clear_charges('amq')
        self.assertEqual(self.consumer.log, [(
            'people', {
                '$time': int(self.mp._now() * 1000),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$unset': [ '$transactions' ],
            }
        )])

    def test_alias(self):
        self.mp.alias('ALIAS','ORIGINAL ID')
        self.assertEqual(self.consumer.log, [(
            'events', {
                'event': '$create_alias',
                'properties': {
                    'token': self.TOKEN,
                    'distinct_id': 'ORIGINAL ID',
                    'alias': 'ALIAS',
                    'time': int(self.mp._now()),
                    'mp_lib': 'python',
                    '$lib_version': mixpanel.VERSION,
                },
            }

        )])

    def test_people_meta(self):
        self.mp.people_set('amq', {'birth month': 'october', 'favorite color': 'purple'},
            meta={'$ip': 0, '$ignore_time': True})
        self.assertEqual(self.consumer.log, [(
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
        )])

class ConsumerTestCase(unittest.TestCase):
    def setUp(self):
        self.consumer = mixpanel.Consumer()

    @contextlib.contextmanager
    def _assertSends(self, expect_url, expect_data):
        mock_response = MagicMock()
        mock_response.read.return_value = '{"status":1, "error": null}'.encode('utf-8')
        with patch('urllib.request.urlopen', return_value = mock_response) as urlopen:
            yield

            self.assertEqual(urlopen.call_count, 1)
            ((request,), _) = urlopen.call_args
            self.assertEqual(request.full_url, expect_url)
            # Converting data into sets since the order might not be preserved
            self.assertEqual(set(request.data.decode('utf-8').split('&')),
                             set(expect_data.split('&')))

    def test_send_events(self):
        with self._assertSends('https://api.mixpanel.com/track', 'ip=0&data=IkV2ZW50Ig%3D%3D&verbose=1'):
            self.consumer.send('events', '"Event"')

    def test_send_people(self):
        with self._assertSends('https://api.mixpanel.com/engage','ip=0&data=IlBlb3BsZSI%3D&verbose=1'):
            self.consumer.send('people', '"People"')

class BufferedConsumerTestCase(unittest.TestCase):
    def setUp(self):
        self.MAX_LENGTH = 10
        self.consumer = mixpanel.BufferedConsumer(self.MAX_LENGTH)
        self.mock = MagicMock()
        self.mock.read.return_value = '{"status":1, "error": null}'.encode('utf-8')

    def test_buffer_hold_and_flush(self):
        with patch('urllib.request.urlopen', return_value = self.mock) as urlopen:
            self.consumer.send('events', '"Event"')
            self.assertTrue(not self.mock.called)
            self.consumer.flush()

            self.assertEqual(urlopen.call_count, 1)
            ((request,), _) = urlopen.call_args
            self.assertEqual(request.full_url, 'https://api.mixpanel.com/track')
            self.assertEqual(set(request.data.decode('utf-8').split('&')),
                             set('ip=0&data=WyJFdmVudCJd&verbose=1'.split('&')))

    def test_buffer_fills_up(self):
        with patch('urllib.request.urlopen', return_value = self.mock) as urlopen:
            for i in range(self.MAX_LENGTH - 1):
                self.consumer.send('events', '"Event"')
                self.assertTrue(not self.mock.called)

            self.consumer.send('events', '"Last Event"')

            self.assertEqual(urlopen.call_count, 1)
            ((request,),_) = urlopen.call_args
            self.assertEqual(request.full_url, 'https://api.mixpanel.com/track')
            self.assertEqual(set(request.data.decode('utf-8').split('&')),
                             set('ip=0&data=WyJFdmVudCIsIkV2ZW50IiwiRXZlbnQiLCJFdmVudCIsIkV2ZW50IiwiRXZlbnQiLCJFdmVudCIsIkV2ZW50IiwiRXZlbnQiLCJMYXN0IEV2ZW50Il0%3D&verbose=1'.split('&')))

class FunctionalTestCase(unittest.TestCase):
    def setUp(self):
        self.TOKEN = '12345'
        self.mp = mixpanel.Mixpanel(self.TOKEN)
        self.mp._now = lambda : 1000

    @contextlib.contextmanager
    def _assertRequested(self, expect_url, expect_data):
        mock_response = MagicMock()
        mock_response.read.return_value = '{"status":1, "error": null}'.encode('utf-8')
        with patch('urllib.request.urlopen', return_value = mock_response) as urlopen:
            yield

            self.assertEqual(urlopen.call_count, 1)
            ((request,), _) = urlopen.call_args
            self.assertEqual(request.full_url, expect_url)
            data = urllib.parse.parse_qs(request.data.decode('utf-8'))
            self.assertEqual(len(data['data']), 1)
            payload_encoded = data['data'][0]
            payload_json = base64.b64decode(payload_encoded).decode('utf-8')

            payload = json.loads(payload_json)
            self.assertEqual(payload, expect_data)

    def test_track_functional(self):
        # XXX this includes $lib_version, which means the test breaks
        # every time we release.
        expect_data = {'event': {'color': 'blue', 'size': 'big'}, 'properties': {'mp_lib': 'python', 'token': '12345', 'distinct_id': 'button press', '$lib_version': mixpanel.VERSION, 'time': 1000}}
        with self._assertRequested('https://api.mixpanel.com/track', expect_data):
            self.mp.track('button press', {'size': 'big', 'color': 'blue'})

    def test_people_set_functional(self):
        expect_data = {'$distinct_id': 'amq', '$set': {'birth month': 'october', 'favorite color': 'purple'}, '$time': 1000000, '$token': '12345'}
        with self._assertRequested('https://api.mixpanel.com/engage', expect_data):
             self.mp.people_set('amq', {'birth month': 'october', 'favorite color': 'purple'})

if __name__ == "__main__":
    unittest.main()
