import base64
import json
import urllib
import urllib2

class Mixpanel(object):

    def __init__(self, token, base_url='https://api.mixpanel.com/'):
        """
        To use mixpanel, create a new Mixpanel object using your token.
        Use this object to start tracking.
        Example:
            mp = Mixpanel('36ada5b10da39a1347559321baf13063')
        """
        self._token = token
        self._base_url = base_url

    @classmethod
    def _encode_data(self, data):
        return urllib.urlencode({'data': base64.b64encode(json.dumps(data)),'verbose':1})

    def _write_request(self, base_url, endpoint, request, batch=False):
        """
        Writes a request taking in either 'track/' for events or 'engage/' for
        people.
        """
        data = self._encode_data(request)
        request_url = ''.join([base_url, endpoint])
        try:
            if not batch:
                response = urllib2.urlopen(request_url, data).read()
            else:
                batch_request = urllib2.Request(request_url, data)
                response = urllib2.urlopen(batch_request).read()

        except urllib2.HTTPError as e:
            raise e
        return response == '1'

    def _people(self, distinct_id, update_type, properties):
        record = {
            '$token': self._token,
            '$distinct_id': distinct_id,
            update_type: properties,
        }
        return self._write_request(self._base_url, 'engage/', record)

    def track(self, event_name, properties={}):
        """
        For basic event tracking. Should pass in name of event name and
        dictionary of properties.
        Example:
            mp.track('clicked button', { 'color': 'blue', 'text': 'no' })
        """
        all_properties = { 'token' : self._token }
        all_properties.update(properties)
        event = {
            'event': event_name,
            'properties': all_properties,
        }
        return self._write_request(self._base_url, 'track/', event)

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
        return self._write_request(self._base_url, 'engage/', record)

    def people_set(self, distinct_id, properties):
        return self._people(distinct_id, '$set', properties)

    def people_set_once(self, distinct_id, properties):
        return self._people(distinct_id, '$set_once', properties)

    def people_add(self, distinct_id, properties):
        return self._people(distinct_id, '$add', properties)

    def people_append(self, distinct_id, properties):
        return self._people(distinct_id, '$append', properties)

    def people_union(self, distinct_id, properties):
        return self._people(distinct_id, '$union', properties)

    def people_unset(self, distinct_id, properties):
        return self._people(distinct_id, '$unset', properties)

    def people_delete(self, distinct_id):
        return self._people(distinct_id, '$delete', "")

    def send_people_batch(self, data):
        return self._write_request(self._base_url, 'engage/', data, batch=True)

    def send_events_batch(self, data):
        return self._write_request(self._base_url, 'track/', data, batch=True)
