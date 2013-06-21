import base64
import json
import urllib
import urllib2

class Mixpanel(object):
    def __init__(self, token, base_url='https://api.mixpanel.com/'):
        self._token = token
        self._base_url = base_url

    def _write_request(self, endpoint, request):
        data = urllib.urlencode({'data': base64.b64encode(json.dumps(request))})
        try:
            response = urllib2.urlopen(''.join([self._base_url,endpoint]), data).read()
        except urllib2.HTTPError as e:
            # remove when done with development
            print e.read()
            raise e
        if response == '1':
            # remove when done with development 
            print 'success' 
        else:
            raise RuntimeError('%s failed', endpoint)

    def _send_batch(self, endpoint, request): 
        data = urllib.urlencode({'data': base64.b64encode(json.dumps(request))})
        try:
            request = urllib2.Request(''.join([self._base_url, endpoint]), data)
            response = urllib2.urlopen(request).read()
        except urllib2.HTTPError as e:
            # remove when done with development
            print e.read()
            raise e
        if response == '1':
            # remove when done with development 
            print 'success' 
        else:
            raise RuntimeError('%s failed', endpoint)

    def track(self, event_name, properties, geolocate_ip=False, verbose=True):
        assert(type(event_name) == str), "event_name not a string"
        assert(len(event_name) > 0), "event_name empty string"
        assert(type(properties) == dict), "properties not dictionary"
        all_properties = { '$token' : self._token }
        all_properties.update(properties)
        all_properties.update( {'ip': (0 if not geolocate_ip else 1), 'verbose': verbose} )
        event = {
            'event': event_name,
            'properties': all_properties, 
        }
        self._write_request('track/', event)

    def engage_update(self, distinct_id, update_type, properties):
        assert(type(update_type) == str), "update_type not a string"
        assert(len(update_type) > 0), "update_type empty string"
        assert(type(properties) == dict), "properties not dictionary"
        record = {
            '$token': self._token,
            '$distinct_id': distinct_id,
             update_type: properties,
        }
        self._write_request('engage/', record)

    def alias(self, alias_id, original):
        record = {
            'event': '$create_alias',
            'properties': {
                'distinct_id': original, 
                'alias': alias_id,
                'token': self._token,
            } 
        }
        self._write_request('engage/', record)

    def send_events_batch(self, data):
        self.__send_batch(data, 'track/')

    def send_people_batch(self, data):
        self.__send_batch(data, 'engage/')


