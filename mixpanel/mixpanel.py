import base64
import json
import time
import urllib
import urllib2

class Mixpanel(object):

    def __init__(self, token, base_url='https://api.mixpanel.com/'):
        """
        Creates a new Mixpanel object, which can be used for all tracking.

        To use mixpanel, create a new Mixpanel object using your token.
        Use this object to start tracking.
        Takes in a user token and an optional base url. Base url defaults to
        https://api.mixpanel.com.
        Example:
            mp = Mixpanel('36ada5b10da39a1347559321baf13063')
        """
        self._token = token
        self._base_url = base_url

    def _now():
        return int(time.time())

    @classmethod
    def _prepare_data(self, data):
        return urllib.urlencode({'data': base64.b64encode(json.dumps(data)),'verbose':1})

    def _write_request(self, base_url, endpoint, request, batch=False):
        data = self._prepare_data(request)
        request_url = ''.join([base_url, endpoint])
        try:
            if not batch:
                response = urllib2.urlopen(request_url, data).read()
            else:
                batch_request = urllib2.Request(request_url, data)
                response = urllib2.urlopen(batch_request).read()

        except urllib2.HTTPError as e:
            raise e

        try:
            response = json.loads(response)
        except ValueError:
            raise Exception('Cannot interpret Mixpanel server response: {0}'.format(response))

        if response['status'] != 1:
            raise Exception('Mixpanel error: {0}'.format(response['error']))

        return True

    def _people(self, distinct_id, update_type, properties):
        record = {
            '$token': self._token,
            '$distinct_id': distinct_id,
            update_type: properties,
        }
        return self._write_request(self._base_url, 'engage/', record)

    def track(self, distinct_id, event_name, properties={}):
        """
        Notes that an event has occurred, along with a distinct_id
        representing the source of that event (for example, a user id),
        an event name describing the event and a set of properties
        describing that event. Properties are provided as a Hash with
        string keys and strings, numbers or booleans as values.

          # Track that user "12345"'s credit card was declined
          mp.track("12345", "Credit Card Declined")

          # Properties describe the circumstances of the event,
          # or aspects of the source or user associated with the event
          mp.track("12345", "Welcome Email Sent", {
              'Email Template' => 'Pretty Pink Welcome',
              'User Sign-up Cohort' => 'July 2013'
          })
        """
        all_properties = {
            'token' : self._token,
            'distinct_id': distinct_id,
            'time': self._now(),
            'mp_lib': 'python',
        }
        all_properties.update(properties)
        event = {
            'event': event_name,
            'properties': all_properties,
        }
        return self._write_request(self._base_url, 'track/', event)

    def alias(self, alias_id, original):
        """
        Gives custom alias to a people record.

        Alias sends an update to our servers linking an existing distinct_id
        with a new id, so that events and profile updates associated with the
        new id will be associated with the existing user's profile and behavior.
        Example:
            mp.alias('amy@mixpanel.com', '13793')
        """
        self.track(original, '$create_alias', {
            'distinct_id': original,
            'alias': alias_id,
            'token': self._token,
        })

    def people_set(self, distinct_id, properties):
        """
        Set properties of a people record.

        Sets properties of a people record given in JSON object. If the profile
        does not exist, creates new profile with these properties.
        Example:
            mp.people_set('12345', {'Address': '1313 Mockingbird Lane',
                                    'Birthday': '1948-01-01'})
        """
        return self._people(distinct_id, '$set', properties)

    def people_set_once(self, distinct_id, properties):
        """
        Set immutable properties of a people record.

        Sets properties of a people record given in JSON object. If the profile
        does not exist, creates new profile with these properties. Does not
        overwrite existing property values.
        Example:
            mp.people_set_once('12345', {'First Login': "2013-04-01T13:20:00"})
        """
        return self._people(distinct_id, '$set_once', properties)

    def people_add(self, distinct_id, properties):
        """
        Increments/decrements numerical properties of people record.

        Takes in JSON object with keys and numerical values. Adds numerical
        values to current property of profile. If property doesn't exist adds
        value to zero. Takes in negative values for subtraction.
        Example:
            mp.people_add('12345', {'Coins Gathered': 12})
        """
        return self._people(distinct_id, '$add', properties)

    def people_append(self, distinct_id, properties):
        """
        Appends to the list associated with a property.

        Takes a JSON object containing keys and values, and appends each to a
        list associated with the corresponding property name. $appending to a
        property that doesn't exist will result in assigning a list with one
        element to that property.
        Example:
            mp.people_append('12345', { "Power Ups": "Bubble Lead" })
        """
        return self._people(distinct_id, '$append', properties)

    def people_union(self, distinct_id, properties):
        """
        Merges the values for a list associated with a property.

        Takes a JSON object containing keys and list values. The list values in
        the request are merged with the existing list on the user profile,
        ignoring duplicate list values.
        Example:
            mp.people_union('12345', { "Items purchased": ["socks", "shirts"] } )
        """
        return self._people(distinct_id, '$union', properties)

    def people_unset(self, distinct_id, properties):
        """
        Removes properties from a profile.

        Takes a JSON list of string property names, and permanently removes the
        properties and their values from a profile.
        Example:
            mp.people_unset('12345', ["Days Overdue"])
        """
        return self._people(distinct_id, '$unset', properties)

    def people_delete(self, distinct_id):
        """
        Permanently deletes a profile.

        Permanently delete the profile from Mixpanel, along with all of its
        properties.
        Example:
            mp.people_delete('12345')
        """
        return self._people(distinct_id, '$delete', "")

    def track_charge(self, distinct_id, amount, properties={}):
        """
        Tracks a charge to a user.

        Record that you have charged the current user a certain amount of
        money. Charges recorded with track_charge will appear in the Mixpanel
        revenue report.
        Example:
            #tracks a charge of $50 to user '1234'
            mp.track_charge('1234', 50)

            #tracks a charge of $50 to user '1234' at a specific time
            mp.track_charge('1234', 50, {'$time': "2013-04-01T09:02:00"})
        """
        properties.update({'$amount': amount})
        return self.people_append(distinct_id, {'$transactions': properties})

    def send_people_batch(self, data):
       """
       Sends list of up to 50 people records.

       Takes in list of JSON objects, up to 50 people records.
       Example:
       data = [
               {
                   "$token": "36ada5b10da39a1347559321baf13063",
                   "$distinct_id": "13793",
                   "$set": {
                       "$first_name": "Joe",
                       "$last_name": "Doe",
                       "$email": "joe.doe@example.com",
                       "$created": "2013-04-01T13:20:00",
                       "$phone": "4805551212"
                       }
               }
              ]
       mp.send_people_batch(data)
       """
       return self._write_request(self._base_url, 'engage/', data, batch=True)

    def send_events_batch(self, data):
        """
        Sends list of up to 50 events.

        Takes in list of JSON objects, up to 50 events records.
        Example:
        data = [
                {
                    "event": "Signed Up",
                    "properties": {
                    "distinct_id": "13793",
                    "token": "e3bc4100330c35722740fb8c6f5abddc",
                    "Referred By": "Friend",
                    "time": 1371002000
                    }
                },
                {
                    "event": "Uploaded Photo",
                    "properties": {
                    "distinct_id": "13793",
                    "token": "e3bc4100330c35722740fb8c6f5abddc",
                    "Topic": "Vacation",
                    "time": 1371002104
                    }
                }
               ]
        mp.send_events_batch(data)
        """
        return self._write_request(self._base_url, 'track/', data, batch=True)
