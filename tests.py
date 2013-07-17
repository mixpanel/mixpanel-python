#!/usr/bin/env python
import urllib
import unittest
from mixpanel import Mixpanel
from mock import Mock, patch

class MixpanelTestCase(unittest.TestCase):
    track_request_url = 'https://api.mixpanel.com/track/'
    engage_request_url = 'https://api.mixpanel.com/engage/'

    def test_constructor(self):
        token = '12345'
        mp = Mixpanel(token)
        self.assertEqual(mp._token, token)

    def test_prepare_data(self):
        prepared_ab = Mixpanel._prepare_data({'a': 'b'})
        self.assertEqual('data=eyJhIjogImIifQ%3D%3D&verbose=1', prepared_ab)

    def test_track(self):
        token = '12345'
        mp = Mixpanel(token)
        mock_response = Mock()
        mock_response.read.return_value = '1'
        with patch('urllib2.urlopen', return_value = mock_response) as mock_urlopen:
            mp.track('button press', {'size': 'big', 'color': 'blue'})
        data = mp._prepare_data({'event': 'button press', 'properties': {'token': '12345', 'size': 'big', 'color': 'blue'}})
        mock_urlopen.assert_called_once_with(self.track_request_url, data)

    def test_people_set(self):
        token = '12345'
        mp = Mixpanel(token)
        mock_response = Mock()
        mock_response.read.return_value = '1'
        with patch('urllib2.urlopen', return_value = mock_response) as mock_urlopen:
            mp.people_set('amq', {'birth month': 'october', 'favorite color': 'purple'})
        data = mp._prepare_data({'$token': '12345', '$distinct_id': 'amq', '$set': {'birth month': 'october', 'favorite color': 'purple'}})
        mock_urlopen.assert_called_once_with(self.engage_request_url, data)

    def test_alias(self):
        token = '12345'
        mp = Mixpanel(token)
        mock_response = Mock()
        mock_response.read.return_value = '1'
        with patch('urllib2.urlopen', return_value = mock_response) as mock_urlopen:
            mp.alias('amq','3680')
        data = mp._prepare_data({'event': '$create_alias', 'properties': {'distinct_id': '3680', 'alias': 'amq', 'token': '12345'}})
        mock_urlopen.assert_called_once_with(self.track_request_url, data)

    def test_events_batch(self):
        events_list = [
            {
                "event": "Signed Up",
                "properties": {
                    "distinct_id": "13793",
                     "token": "e3bc4100330c35722740fb8c6f5abddc",
                     "Referred By": "Friend",
                     "time": 1371002000
                }
            },
            {
                "event": "Uploaded Photo",
                "properties": {
                    "distinct_id": "13793",
                    "token": "e3bc4100330c35722740fb8c6f5abddc",
                    "Topic": "Vacation",
                    "time": 1371002104
                }
            }
        ]
        token = "e3bc4100330c35722740fb8c6f5abddc"
        mp = Mixpanel(token)
        mock_response = Mock()
        mock_response.read.return_value = '1'
        data = mp._prepare_data(events_list)
        with patch('urllib2.Request', return_value = mock_response) as mock_Request:
            with patch('urllib2.urlopen', return_value = mock_response) as mock_urlopen:
                mp.send_events_batch(events_list)
        mock_Request.assert_called_once_with(self.track_request_url, data)

if __name__ == "__main__":
    unittest.main()
