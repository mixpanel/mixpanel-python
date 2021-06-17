from __future__ import absolute_import, unicode_literals
import datetime
import decimal
import json
import time

import pytest
import responses
import six
from six.moves import range, urllib


import mixpanel


class LogConsumer(object):
    def __init__(self):
        self.log = []

    def send(self, endpoint, event, api_key=None, api_secret=None):
        entry = [endpoint, json.loads(event)]
        if api_key != (None, None):
            if api_key:
                entry.append(api_key)
            if api_secret:
                entry.append(api_secret)
        self.log.append(tuple(entry))

    def clear(self):
        self.log = []


class TestMixpanel:
    TOKEN = '12345'

    def setup_method(self, method):
        self.consumer = LogConsumer()
        self.mp = mixpanel.Mixpanel(self.TOKEN, consumer=self.consumer)
        self.mp._now = lambda: 1000.1
        self.mp._make_insert_id = lambda: "abcdefg"

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

    def test_track_makes_insert_id(self):
        self.mp.track('ID', 'button press', {'size': 'big'})
        props = self.consumer.log[0][1]["properties"]
        assert "$insert_id" in props
        assert isinstance(props["$insert_id"], six.text_type)
        assert len(props["$insert_id"]) > 0

    def test_track_empty(self):
        self.mp.track('person_xyz', 'login', {})
        assert self.consumer.log == [(
            'events', {
                'event': 'login',
                'properties': {
                    'token': self.TOKEN,
                    'distinct_id': 'person_xyz',
                    'time': int(self.mp._now()),
                    '$insert_id': self.mp._make_insert_id(),
                    'mp_lib': 'python',
                    '$lib_version': mixpanel.__version__,
                },
            },
        )]

    def test_import_data(self):
        timestamp = time.time()
        self.mp.import_data('MY_API_KEY', 'ID', 'button press', timestamp,
            {'size': 'big', 'color': 'blue', '$insert_id': 'abc123'},
            api_secret='MY_SECRET')
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
            ('MY_API_KEY', 'MY_SECRET'),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$unset': ['Albums', 'Singles'],
            }
        )]

    def test_people_remove(self):
        self.mp.people_remove('amq', {'Albums': 'Diamond Dogs'})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now()),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$remove': {'Albums': 'Diamond Dogs'},
            }
        )]

    def test_people_track_charge(self):
        self.mp.people_track_charge('amq', 12.65, {'$time': '2013-04-01T09:02:00'})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
                '$token': self.TOKEN,
                '$distinct_id': 'amq',
                '$set': {
                    '$created': '2014-02-14T01:02:03',
                    'favorite color': 'purple',
                },
            }
        )]

    @responses.activate
    def test_alias(self):
        # More complicated since alias() forces a synchronous call.
        responses.add(
            responses.POST,
            'https://api.mixpanel.com/track',
            json={"status": 1, "error": None},
            status=200,
        )

        self.mp.alias('ALIAS', 'ORIGINAL ID')
        assert self.consumer.log == []
        assert len(responses.calls) == 1
        call = responses.calls[0]
        assert call.request.method == "POST"
        assert call.request.url == "https://api.mixpanel.com/track"
        posted_data = dict(urllib.parse.parse_qsl(six.ensure_str(call.request.body)))
        assert json.loads(posted_data["data"]) == {"event":"$create_alias","properties":{"alias":"ALIAS","token":"12345","distinct_id":"ORIGINAL ID"}}

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
            ('my_good_api_key', None),
        )]

        self.consumer.clear()

        self.mp.merge('my_good_api_key', 'd1', 'd2', api_secret='my_secret')
        assert self.consumer.log == [(
            'imports',
            {
                'event': '$merge',
                'properties': {
                    '$distinct_ids': ['d1', 'd2'],
                    'token': self.TOKEN,
                }
            },
            ('my_good_api_key', 'my_secret'),
        )]

    def test_people_meta(self):
        self.mp.people_set('amq', {'birth month': 'october', 'favorite color': 'purple'},
                           meta={'$ip': 0, '$ignore_time': True})
        assert self.consumer.log == [(
            'people', {
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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
                '$time': int(self.mp._now()),
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

    @responses.activate
    def test_send_events(self):
        responses.add(
            responses.POST,
            'https://api.mixpanel.com/track',
            json={"status": 1, "error": None},
            status=200,
            match=[responses.urlencoded_params_matcher({"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'})],
        )
        self.consumer.send('events', '{"foo":"bar"}')
        assert len(responses.calls) == 1

    @responses.activate
    def test_send_people(self):
        responses.add(
            responses.POST,
            'https://api.mixpanel.com/engage',
            json={"status": 1, "error": None},
            status=200,
            match=[responses.urlencoded_params_matcher({"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'})],
        )
        self.consumer.send('people', '{"foo":"bar"}')
        assert len(responses.calls) == 1

    @responses.activate
    def test_server_success(self):
        responses.add(
            responses.POST,
            'https://api.mixpanel.com/track',
            json={"status": 1, "error": None},
            status=200,
            match=[responses.urlencoded_params_matcher({"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'})],
        )
        self.consumer.send('events', '{"foo":"bar"}')
        assert len(responses.calls) == 1

    @responses.activate
    def test_server_invalid_data(self):
        error_msg = "bad data"
        responses.add(
            responses.POST,
            'https://api.mixpanel.com/track',
            json={"status": 0, "error": error_msg},
            status=200,
            match=[responses.urlencoded_params_matcher({"ip": "0", "verbose": "1", "data": '{INVALID "foo":"bar"}'})],
        )

        with pytest.raises(mixpanel.MixpanelException) as exc:
            self.consumer.send('events', '{INVALID "foo":"bar"}')
        assert len(responses.calls) == 1
        assert error_msg in str(exc)

    @responses.activate
    def test_server_unauthorized(self):
        responses.add(
            responses.POST,
            'https://api.mixpanel.com/track',
            json={"status": 0, "error": "unauthed"},
            status=401,
            match=[responses.urlencoded_params_matcher({"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'})],
        )
        with pytest.raises(mixpanel.MixpanelException) as exc:
            self.consumer.send('events', '{"foo":"bar"}')
        assert len(responses.calls) == 1
        assert "unauthed" in str(exc)

    @responses.activate
    def test_server_forbidden(self):
        responses.add(
            responses.POST,
            'https://api.mixpanel.com/track',
            json={"status": 0, "error": "forbade"},
            status=403,
            match=[responses.urlencoded_params_matcher({"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'})],
        )
        with pytest.raises(mixpanel.MixpanelException) as exc:
            self.consumer.send('events', '{"foo":"bar"}')
        assert len(responses.calls) == 1
        assert "forbade" in str(exc)

    @responses.activate
    def test_server_5xx(self):
        responses.add(
            responses.POST,
            'https://api.mixpanel.com/track',
            body="Internal server error",
            status=500,
            match=[responses.json_params_matcher({"ip": 0, "verbose": 1, "data": '{"foo":"bar"}'})],
        )
        with pytest.raises(mixpanel.MixpanelException) as exc:
            self.consumer.send('events', '{"foo":"bar"}')
        assert len(responses.calls) == 1

    @responses.activate
    def test_consumer_override_api_host(self):
        consumer = mixpanel.Consumer(api_host="api-zoltan.mixpanel.com")

        responses.add(
            responses.POST,
            'https://api-zoltan.mixpanel.com/track',
            json={"status": 1, "error": None},
            status=200,
            match=[responses.urlencoded_params_matcher({"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'})],
        )
        consumer.send('events', '{"foo":"bar"}')
        assert len(responses.calls) == 1

        responses.add(
            responses.POST,
            'https://api-zoltan.mixpanel.com/engage',
            json={"status": 1, "error": None},
            status=200,
            match=[responses.urlencoded_params_matcher({"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'})],
        )
        consumer.send('people', '{"foo":"bar"}')
        assert len(responses.calls) == 2

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

    @responses.activate
    def test_useful_reraise_in_flush_endpoint(self):
        responses.add(
            responses.POST,
            'https://api.mixpanel.com/track',
            json={"status": 0, "error": "arbitrary error"},
            status=200,
        )

        broken_json = '{broken JSON'
        consumer = mixpanel.BufferedConsumer(2)
        consumer.send('events', broken_json)

        with pytest.raises(mixpanel.MixpanelException) as excinfo:
            consumer.flush()
        assert excinfo.value.message == '[%s]' % broken_json
        assert excinfo.value.endpoint == 'events'

        assert len(responses.calls) == 1

    def test_send_remembers_api_key(self):
        self.consumer.send('imports', '"Event"', api_key='MY_API_KEY')
        assert len(self.log) == 0
        self.consumer.flush()
        assert self.log == [('imports', ['Event'], ('MY_API_KEY', None))]

    def test_send_remembers_api_secret(self):
        self.consumer.send('imports', '"Event"', api_secret='ZZZZZZ')
        assert len(self.log) == 0
        self.consumer.flush()
        assert self.log == [('imports', ['Event'], (None, 'ZZZZZZ'))]




class TestFunctional:
    @classmethod
    def setup_class(cls):
        cls.TOKEN = '12345'
        cls.mp = mixpanel.Mixpanel(cls.TOKEN)
        cls.mp._now = lambda: 1000

    @responses.activate
    def test_track_functional(self):
        responses.add(
            responses.POST,
            'https://api.mixpanel.com/track',
            json={"status": 1, "error": None},
            status=200,
        )

        self.mp.track('player1', 'button_press', {'size': 'big', 'color': 'blue', '$insert_id': 'xyz1200'})

        assert len(responses.calls) == 1
        body = six.ensure_str(responses.calls[0].request.body)
        wrapper = dict(urllib.parse.parse_qsl(body))
        data = json.loads(wrapper["data"])
        del wrapper["data"]

        assert {"ip": "0", "verbose": "1"} == wrapper
        expected_data = {'event': 'button_press', 'properties': {'size': 'big', 'color': 'blue', 'mp_lib': 'python', 'token': '12345', 'distinct_id': 'player1', '$lib_version': mixpanel.__version__, 'time': 1000, '$insert_id': 'xyz1200'}}
        assert expected_data == data

    @responses.activate
    def test_people_set_functional(self):
        responses.add(
            responses.POST,
            'https://api.mixpanel.com/engage',
            json={"status": 1, "error": None},
            status=200,
        )

        self.mp.people_set('amq', {'birth month': 'october', 'favorite color': 'purple'})
        assert len(responses.calls) == 1
        body = six.ensure_str(responses.calls[0].request.body)
        wrapper = dict(urllib.parse.parse_qsl(body))
        data = json.loads(wrapper["data"])
        del wrapper["data"]

        assert {"ip": "0", "verbose": "1"} == wrapper
        expected_data = {'$distinct_id': 'amq', '$set': {'birth month': 'october', 'favorite color': 'purple'}, '$time': 1000, '$token': '12345'}
        assert expected_data == data
