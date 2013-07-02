import base64
import json
import urllib
import urllib2

def encode_data(data):
    return urllib.urlencode({'data': base64.b64encode(json.dumps(data))})

def write_request(base_url, endpoint, request):
    """ 
    Writes a request taking in either 'track/' for events or 'engage/' for
    people.
    """ 
    data = encode_data(request) 
    try:
        response = urllib2.urlopen(''.join([base_url, endpoint]), data).read()
    except urllib2.HTTPError as e:
        raise e
    return response == '1'
 
def send_batch(base_url, endpoint, batch): 
    """ 
    Sends a list of events or people in a POST request. Useful if sending a lot
    of requests at once.
    """
    if len(batch) > 50:
        raise 
    for item in batch:
        # TODO test this hardcore
        item['properties'] = item['properties'].update({'token': self._token})
        data = self._encode_data(batch) 
    try:
        batch = urllib2.Request(''.join([self._base_url, endpoint]), data)
        response = urllib2.urlopen(batch).read()
    except urllib2.HTTPError as e:
        raise e
    return response == '1'

class Mixpanel(object):
    class People(object): 
        def __init__(self, token, base_url): 
            self._token = token 
            self._base_url = base_url

        def _people(self, distinct_id, update_type, properties):
            record = {
                '$token': self._token,
                '$distinct_id': distinct_id,
                update_type: properties,
            }
            return write_request(self._base_url, 'engage/', record)

        def set(self, distinct_id, properties):
            return self._people(distinct_id, '$set', properties)
        
        def set_once(self, distinct_id, properties):
            return self._people(distinct_id, '$set_once', properties)

        def add(self, distinct_id, properties):
            return self._people(distinct_id, '$add', properties)

        def append(self, distinct_id, properties):
            return self._people(distinct_id, '$append', properties)

        def union(self, distinct_id, properties):
            return self._people(distinct_id, '$union', properties)

        def unset(self, distinct_id, properties):
            return self._people(distinct_id, '$unset', properties)

        def delete(self, distinct_id):
            return self._people(distinct_id, '$append', "")
    
        def send_people_batch(self, data):
            return send_batch(self._base_url, data, 'engage/')


    def __init__(self, token, base_url='https://api.mixpanel.com/'):
        """ 
        To use mixpanel, create a new Mixpanel object using your token.
        Use this object to start tracking.
        Example:
            mp = Mixpanel('36ada5b10da39a1347559321baf13063')
        """ 
        self._token = token
        self._base_url = base_url
        self.people = self.People(self._token, self._base_url)

    def track(self, event_name, properties={}, verbose=True):
        """ 
        For basic event tracking. Should pass in name of event name and
        dictionary of properties.
        Example:
            mp.track('clicked button', { 'color': 'blue', 'text': 'no' })
        """ 
        all_properties = { 'token' : self._token }
        all_properties.update(properties)
        all_properties.update( { 'verbose': verbose } )
        event = {
            'event': event_name,
            'properties': all_properties, 
        }
        return write_request(self._base_url, 'track/', event)

    def alias(self, alias_id, original):
        """
        Allows you to set a custom alias for people records.
        Example:
            mp.alias('amy@mixpanel.com', '13793')
        """
        record = {
            'event': '$create_alias',
            'properties': {
                'distinct_id': original, 
                'alias': alias_id,
                'token': self._token,
            } 
        }
        return write_request(self._base_url, 'engage/', record)

    def send_events_batch(self, data):
        """
        If sending many events at once, this is useful. Accepts lists of 50 
        events at a time and sends them via a POST request.

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
        send_batch(self._base_url, data, 'track/')
