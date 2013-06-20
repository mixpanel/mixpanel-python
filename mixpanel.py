TRACK_ENDPOINT = "http://api.mixpanel.com/track/"
ENGAGE_ENDPOINT = "http://api.mixpanel.com/engage/"

class Mixpanel:
    __token = None
    __distinct_id = None


    def __write_request__(self, endpoint, request):
        data = urllib.urlencode({'data': base64.b64encode(json.dumps(record))})
        ENDPOINT = ENGAGE_ENDPOINT if (endpoint == "engage") else TRACK_ENDPOINT
        try:
            response = urllib2.urlopen(ENDPOINT, data).read()
        except urllib2.HTTPError as e:
            print e.read()
            raise
        if response == '1':
            # will have to change this
            print 'success' 
        else:
            raise RuntimeError('%s failed', endpoint)

    def __write_event__(self, event):
        self.__write_request__('track', event)

    def __write_record__(self, record):
        self.__write_request__('engage', record)

    def track(event_name, properties, ip=0, verbose=False):
        properties.update( {"ip": ip, "verbose": verbose} )
        event = {
                    "event": event_name,
                    "properties": properties, 
                }
        self.__write_event__(event)

    def __engage_update_(self, update_type, properties):
        record = {
                     "token": self.__token,
                     "$distinct_id": self.__distinct_id,
                     update_type: properties,
                 }
        self.__write_record__(record)

    def identify(self, some_id):
        self.__distinct_id = some_id

    def alias(self, alias_id, original=__distinct_id):
        record = {
                     "event": "$create_alias",
                     "properties": {
                         "distinct_id": self.__distinct_id,
                         "alias": alias_id,
                         "token": self.__token,
                     } 
                 }

    def people_set(self, properties):
        __engage_update__(self, "$set", properties)

    def people_set_once(self, properties):
        __engage_update__(self, "$set_once", properties)

    def people_add(self, properties):
        __engage_update__(self, "$add", properties)

    def people_append(self, properties):
        __engage_update__(self, "$append", properties)

    def people_union(self, properties):
        __engage_update__(self, "$union", properties)

    def people_unset(self, properties):
        __engage_update__(self, "$unset", properties)

    def people_delete(self):
        __engage_update__(self, "$delete", "")

