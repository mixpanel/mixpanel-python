import urllib
import urllib2
import base64
import json

class Mixpanel:
    _track_endpoint = "http://api.mixpanel.com/track/"
    _engage_endpoint = "http://api.mixpanel.com/engage/"
    _token = None
    _distinct_id = None

    def __init__(self, token):
        _token = token

    def _write_request(self, endpoint, request):
        data = urllib.urlencode({'data': base64.b64encode(json.dumps(request))})
        try:
            response = urllib2.urlopen(endpoint, data).read()
        except urllib2.HTTPError as e:
            # remove when done with development
            print e.read()
            raise e
        if response == '1':
            # remove when done with development 
            print 'success' 
        else:
            raise RuntimeError('%s failed', endpoint)

    def _write_event(self, event):
        self._write_request(self._track_endpoint, event)

    def _write_record(self, record, distinct_id):
        self._distinct_id = distinct_id
        self._write_request(self._engage_endpoint, record)

    def track(self, event_name, properties, ip=0, verbose=False):
        properties.update( {"ip": ip, "verbose": verbose} )
        event = {
            "event": event_name,
            "properties": properties, 
        }
        self._write_event(event)

    def identify(self, distinct_id):
        self._distinct_id = distinct_id

    def _engage_update(self, update_type, properties, distinct_id=_distinct_id):
        record = {
            "token": self._token,
            "$distinct_id": distinct_id,
             update_type: properties,
        }
        self._write_record(record)

    def alias(self, alias_id, distinct_id=_distinct_id):
        record = {
            "event": "$create_alias",
            "properties": {
                "distinct_id": distinct_id,
                "alias": alias_id,
                "token": self._token,
            } 
        }

    def people_set(self, properties, distinct_id=_distinct_id):
        self._engage_update("$set", properties, distinct_id)

    def people_set_once(self, properties, distinct_id=_distinct_id):
        self._engage_update("$set_once", properties, distinct_id)

    def people_add(self, properties, distinct_id=_distinct_id):
        self._engage_update("$add", properties, distinct_id)

    def people_append(self, properties, distinct_id=_distinct_id):
        self._engage_update("$append", properties, distinct_id)

    def people_union(self, properties, distinct_id=_distinct_id):
        self._engage_update("$union", properties, distinct_id)

    def people_unset(self, properties, distinct_id=_distinct_id):
        self._engage_update("$unset", properties, distinct_id)

    def people_delete(self, distinct_id=_distinct_id):
        self._engage_update("$delete", "", distinct_id)
