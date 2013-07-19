import base64
import json
import urllib
import urllib2

'''
The Mixpanel tracking object uses Consumers to send requests to
Mixpanel servers.  The default consumer behavior is a synchronous HTTP
request for every event or profile update, but this can be changed by
providing your own consumer when you construct a Mixpanel object.

A consumer is just an object with a send(endpoint, message) method,
where the endpoint is one of 'events', or 'people', and the message
is a JSON payload to post.
'''

class MixpanelException(Exception): pass

class Consumer(object):
    '''
    The simple consumer sends an HTTP request directly to the Mixpanel service,
    with one request for every call. This is the default consumer for Mixpanel
    objects- if you don't provide your own, you get one of these.
    '''
    def __init__(self, events_url=None, people_url=None):
        self._endpoints = {
            'events': events_url or 'https://api.mixpanel.com/track',
            'people': people_url or 'https://api.mixpanel.com/people',
        }

    def send(self, endpoint, json_message):
        '''
        Record an event or a profile update. Send is the only method
        associated with consumers. Will raise an exception if the endpoint
        doesn't exist, if the server is unreachable or for some reason
        can't process the message.

        All you need to do to write your own consumer is to implement
        a send method of your own.

        :param endpoint: One of 'events' or 'people', the Mixpanel endpoint for sending the data
        :type endpoint: str (one of 'events' or 'people')
        :param json_message: A json message formatted for the endpoint.
        :type json_message: str
        :raises: MixpanelException
        '''
        if endpoint in self._endpoints:
            self._write_request(self._endpoints[endpoint], json_message)
        else:
            raise MixpanelException('No such endpoint "{0}". Valid endpoints are one of {1}'.format(self._endpoints.keys()))

    def _write_request(self, request_url, json_message):
        data = urllib.urlencode({'data': base64.b64encode(json_message),'verbose':1})
        try:
            request = urllib2.Request(request_url, data)
            response = urllib2.urlopen(request).read()
        except urllib2.HTTPError as e:
            raise MixpanelException(e)

        try:
            response = json.loads(response)
        except ValueError:
            raise MixpanelException('Cannot interpret Mixpanel server response: {0}'.format(response))

        if response['status'] != 1:
            raise MixpanelException('Mixpanel error: {0}'.format(response['error']))

        return True

class BufferedConsumer(object):
    '''
    BufferedConsumer works just like Consumer, but holds messages in
    memory and sends them in batches. This can save bandwidth and
    reduce the total amount of time required to post your events.

    Because BufferedConsumers hold events, you need to call flush()
    when you're sure you're done sending them. calls to flush() will
    send all remaining unsent events being held by the BufferedConsumer.
    '''
    def __init__(self, max_size=50, events_url=None, people_url=None):
        self._consumer = Consumer(events_url, people_url)
        self._buffers = {
            'events': [],
            'people': [],
        }
        self._max_size = min(50, max_size)

    def send(self, endpoint, json_message):
        '''
        Record an event or a profile update. Calls to send() will store
        the given message in memory, and (when enough messages have been stored)
        may trigger a request to Mixpanel's servers.

        Calls to send() may throw an exception, but the exception may be
        associated with the message given in an earlier call. If this is the case,
        the resulting MixpanelException e will have members e.message and e.endpoint

        :param endpoint: One of 'events' or 'people', the Mixpanel endpoint for sending the data
        :type endpoint: str (one of 'events' or 'people')
        :param json_message: A json message formatted for the endpoint.
        :type json_message: str
        :raises: MixpanelException
        '''
        if endpoint not in self._buffers:
            raise MixpanelException('No such endpoint "{0}". Valid endpoints are one of {1}'.format(self._buffers.keys()))

        buf = self._buffers[endpoint]
        buf.append(json_message)
        if len(buf) >= self._max_size:
            self._flush_endpoint(endpoint)

    def flush(self):
        '''
        Send all remaining messages to Mixpanel. BufferedConsumers will
        flush automatically when you call send(), but you will need to call
        flush() when you are completely done using the consumer (for example,
        when your application exits) to ensure there are no messages remaining
        in memory.

        Calls to flush() may raise a MixpanelException if there is a problem
        communicating with the Mixpanel servers. In this case, the exception
        thrown will have a message property, containing the text of the message,
        and an endpoint property containing the endpoint that failed.

        :raises: MixpanelException
        '''
        for endpoint in self._buffers.keys():
            self._flush_endpoint(endpoint)

    def _flush_endpoint(self, endpoint):
        buf = self._buffers[endpoint]
        while buf:
            batch = buf[:self._max_size]
            batch_json = '[{0}]'.format(','.join(batch))
            try:
                self._consumer.send(endpoint, batch_json)
            except MixpanelException as e:
                e.message = 'batch_json'
                e.endpoint = endpoint
            buf = buf[self._max_size:]
        self._buffers[endpoint] = buf
