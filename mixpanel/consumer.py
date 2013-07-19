import base64
import json
import urllib
import urllib2

class Consumer(object):
    def __init__(self, events_url=None, people_url=None):
        self._endpoints = {
            'events': events_url or 'https://api.mixpanel.com/track',
            'people': people_url or 'https://api.mixpanel.com/people',
        }

    def send(self, endpoint, json_message):
        self._write_request(self._endpoints[endpoint], json_message)

    def _write_request(self, request_url, json_message):
        data = urllib.urlencode({'data': base64.b64encode(json_message),'verbose':1})
        try:
            request = urllib2.Request(request_url, data)
            response = urllib2.urlopen(request).read()
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
        self._buffers = {
            'events': [],
            'people': [],
        }
        self._max_size = min(50, max_size)

    def send(self, endpoint, json_message):
        buf = self._buffers[endpoint]
        buf.append(json_message)
        if len(buf) >= self._max_size:
            self._flush_endpoint(endpoint)

    def flush(self):
        for endpoint in self._buffers.keys():
            self._flush_endpoint(endpoint)

    def _flush_endpoint(self, endpoint):
        buf = self._buffers[endpoint]
        while buf:
            batch = buf[:self._max_size]
            batch_json = '[{0}]'.format(','.join(batch))
            self._consumer.send(endpoint, batch_json)
            buf = buf[self._max_size:]
        self._buffers[endpoint] = buf
