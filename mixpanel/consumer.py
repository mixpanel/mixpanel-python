import base64
import json
import urllib
import urllib2

class Consumer(object):
    def __init__(self, events_url=None, people_url=None):
        self._events_url = events_url or "https://api.mixpanel.com/events"
        self._people_url = people_url or "https://api.mixpanel.com/people"

    def send_events(self, json_message):
        self._write_request(self._events_url, json_message)

    def send_people(self, json_message):
        self._write_request(self._people_url, json_message)

    def _write_request(self, request_url, json_message):
        data = urllib.urlencode({'data': base64.b64encode(json_message),'verbose':1})
        try:
            request = urllib2.Request(request_url, data)
            response = urllib2.urlopen(request_url, request).read()
        except urllib2.HTTPError as e:
            raise e

        try:
            response = json.loads(response)
        except ValueError:
            raise Exception('Cannot interpret Mixpanel server response: {0}'.format(response))

        if response['status'] != 1:
            raise Exception('Mixpanel error: {0}'.format(response['error']))

        return True


class BufferedConsumer(object):
    def __init__(self, max_size=50, events_url=None, people_url=None):
        self._consumer = Consumer(events_url, people_url)
        self._events_buffer = []
        self._people_buffer = []
        self._max_size = min(50, max_size)

    def send_events(self, json_message):
        self._events_buffer.append(json_message)
        if len(self._events_buffer) >= self._max_size:
            self._flush_events()

    def send_people(self, json_message):
        self._people_buffer.append(json_message)
        if len(self._people_buffer) >= self._max_size:
            self._flush_people()

    def flush(self):
        self._flush_events()
        self._flush_people()

    def _flush_events(self):
        while self._events_buffer:
            batch = self._events_buffer[:self._max_size]
            batch_json = '[{0}]'.format(','.join(batch))
            self._consumer.send_events(batch_json)
            self._events_buffer = self._events_buffer[self._max_size:]

    def _flush_people(self):
        while self._people_buffer:
            batch = self._people_buffer[:self._max_size]
            batch_json = '[{0}]'.format(','.join(batch))
            self._consumer.send_people(batch_json)
