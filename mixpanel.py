import base64
import json
import urllib
import urllib2

class Mixpanel(object):
    """ 
    To use mixpanel, create a new Mixpanel object using your token.
    Use this object to start tracking.
    Example:
        mp = Mixpanel('36ada5b10da39a1347559321baf13063')
    """ 
    def __init__(self, token, base_url='https://api.mixpanel.com/'):
        self._token = token
        self._base_url = base_url

    """ 
    For internal use. Writes a request taking in either 'track/' for events or
    'engage/' for people. 
    """ 
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

    """ 
    For internal use. Sends a list of events or people in a POST request.
    Useful if sending a lot of requests at once.
    """ 
    def _send_batch(self, endpoint, request): 
        for item in request:
            item['properties'] = item['properties'].update({'token': self._token})
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

    """ 
    For basic event tracking. Should pass in name of event name and dictionary
    of properties.
    Example:
        mp.track('clicked button', { 'color': 'blue', 'text': 'no' })
    """ 
    def track(self, event_name, properties, geolocate_ip=False, verbose=True):
        assert(type(event_name) == str), 'event_name not a string'
        assert(len(event_name) > 0), 'event_name empty string'
        assert(type(properties) == dict), 'properties not dictionary'
        all_properties = { '$token' : self._token }
        all_properties.update(properties)
        all_properties.update( {'ip': (0 if not geolocate_ip else 1), 'verbose': verbose} )
        event = {
            'event': event_name,
            'properties': all_properties, 
        }
        self._write_request('track/', event)

    """
    For all people tracking. Should pass in distinct_id, type of update,
    and dictionary of properties.
    Examples:
        person1 = {
                      'Address': '1313 Mockingbird Lane',
                      'Birthday': '1948-01-01'
                  }
        mp.engage('13793', '$set', person1)
        mp.engage('13793', '$add', { 'Coins Gathered': '12' })
        mp.engage('13793', '$unset', [ 'Birthday' ])
        mp.engage('13793', '$delete', '')
    """
    def engage(self, distinct_id, update_type, properties):
        assert(type(distinct_id) == str), 'distinct_id not a string'
        assert(len(distinct_id) > 0), 'distinct_id empty string'
        assert(type(update_type) == str), 'update_type not a string'
        assert(len(update_type) > 0), 'update_type empty string'
        record = {
            '$token': self._token,
            '$distinct_id': distinct_id,
             update_type: properties,
        }
        self._write_request('engage/', record)

    """
    Allows you to set a custom alias for people records.
    Example:
        mp.alias('amy@mixpanel.com', '13793')
    """
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

    """
    If sending many events at once, this is useful. Accepts lists of 50 events
    at a time and sends them via a POST request.

    Example:

    events_list = [
        {
            "event": "Signed Up",
            "properties": {
                "distinct_id": "13793",
                "Referred By": "Friend",
                "time": 1371002000
            }
        },
        {
             "event": "Uploaded Photo",
              "properties": {
                  "distinct_id": "13793",
                  "Topic": "Vacation",
                  "time": 1371002104
              }
        }
    ]

    mp.send_events_batch(events_list)
    
    """
    def send_events_batch(self, data):
        self.__send_batch(data, 'track/')

    def send_people_batch(self, data):
        self.__send_batch(data, 'engage/')


