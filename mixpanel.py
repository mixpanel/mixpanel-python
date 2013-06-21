class Mixpanel:
    TRACK_ENDPOINT = "http://api.mixpanel.com/track/"
    ENGAGE_ENDPOINT = "http://api.mixpanel.com/engage/"
    _token = None
    _distinct_id = None

    def _write_request(self, endpoint, request):
        data = urllib.urlencode({'data': base64.b64encode(json.dumps(record))})
        try:
            response = urllib2.urlopen(endpoint, data).read()
        except urllib2.HTTPError as e:
            # remove when done with development
            print e.read()
            raise
        if response == '1':
            # remove when done with development 
            print 'success' 
        else:
            raise RuntimeError('%s failed', endpoint)

    def _write_event(self, event):
        self._write_request(TRACK_ENDPOINT, event)

    def _write_record(self, record):
        self._write_request(ENGAGE_ENDPOINT, record)

    def track(event_name, properties, ip=0, verbose=False):
        properties.update( {"ip": ip, "verbose": verbose} )
        event = {
            "event": event_name,
            "properties": properties, 
        }
        self._write_event(event)

    def _engage_update(self, update_type, properties):
        record = {
            "token": self._token,
            "$distinct_id": self._distinct_id,
             update_type: properties,
        }
        self._write_record(record)

    def alias(self, alias_id, original=_distinct_id):
        record = {
            "event": "$create_alias",
            "properties": {
                "distinct_id": self._distinct_id,
                "alias": alias_id,
                "token": self._token,
            } 
        }

    def people_set(self, properties):
        self._engage_update(self, "$set", properties)

    def people_set_once(self, properties):
        self._engage_update(self, "$set_once", properties)

    def people_add(self, properties):
        self._engage_update(self, "$add", properties)

    def people_append(self, properties):
        self._engage_update(self, "$append", properties)

    def people_union(self, properties):
        self._engage_update(self, "$union", properties)

    def people_unset(self, properties):
        self._engage_update(self, "$unset", properties)

    def people_delete(self):
        self._engage_update(self, "$delete", "")

