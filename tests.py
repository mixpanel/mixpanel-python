#!/usr/bin/env python
import urllib
import unittest
from mixpanel import Mixpanel
from mock import Mock, patch

class MixpanelTestCase(unittest.TestCase):
    track_request_url = 'https://api.mixpanel.com/track/'
    engage_request_url = 'https://api.mixpanel.com/engage/'

    def test_track(self):
        token = '12345'
        mp = Mixpanel(token)
        mp._now = lambda : 1000
        mock_response = Mock()
        mock_response.read.return_value = '{"status":1, "error": null}'
        with patch('urllib2.urlopen', return_value = mock_response) as mock_urlopen:
            mp.track('button press', {'size': 'big', 'color': 'blue'})
        mock_urlopen.assert_called_once_with(self.track_request_url, 'data=eyJldmVudCI6IHsiY29sb3IiOiAiYmx1ZSIsICJzaXplIjogImJpZyJ9LCAicHJvcGVydGllcyI6IHsibXBfbGliIjogInB5dGhvbiIsICJ0b2tlbiI6ICIxMjM0NSIsICJkaXN0aW5jdF9pZCI6ICJidXR0b24gcHJlc3MiLCAidGltZSI6IDEwMDB9fQ%3D%3D&verbose=1')

    def test_people_set(self):
        token = '12345'
        mp = Mixpanel(token)
        mp._now = lambda : 1000
        mock_response = Mock()
        mock_response.read.return_value = '{"status":1, "error": null}'
        with patch('urllib2.urlopen', return_value = mock_response) as mock_urlopen:
            mp.people_set('amq', {'birth month': 'october', 'favorite color': 'purple'})
        data = mp._prepare_data({'$token': '12345', '$distinct_id': 'amq', '$set': {'birth month': 'october', 'favorite color': 'purple'}})
        mock_urlopen.assert_called_once_with(self.engage_request_url, data)

    def test_alias(self):
        token = '12345'
        mp = Mixpanel(token)
        mp._now = lambda : 1000
        mock_response = Mock()
        mock_response.read.return_value = '{"status":1, "error": null}'
        with patch('urllib2.urlopen', return_value = mock_response) as mock_urlopen:
            mp.alias('amq','3680')
        mock_urlopen.assert_called_once_with(self.track_request_url, 'data=eyJldmVudCI6ICIkY3JlYXRlX2FsaWFzIiwgInByb3BlcnRpZXMiOiB7ImFsaWFzIjogImFtcSIsICJ0b2tlbiI6ICIxMjM0NSIsICJkaXN0aW5jdF9pZCI6ICIzNjgwIiwgInRpbWUiOiAxMDAwLCAibXBfbGliIjogInB5dGhvbiJ9fQ%3D%3D&verbose=1')

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
        mp._now = lambda : 1000
        mock_response = Mock()
        mock_response.read.return_value = '{"status":1, "error": null}'
        data = mp._prepare_data(events_list)
        with patch('urllib2.Request', return_value = mock_response) as mock_Request:
            with patch('urllib2.urlopen', return_value = mock_response) as mock_urlopen:
                mp.send_events_batch(events_list)
        mock_Request.assert_called_once_with(self.track_request_url, data)

if __name__ == "__main__":
    unittest.main()
