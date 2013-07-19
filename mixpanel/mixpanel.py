import json
import time

from .consumer import Consumer

VERSION = '2.0.0'

class Mixpanel(object):

    def __init__(self, token, consumer=None):
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
        self._consumer = consumer or Consumer()

    def _now(self):
        return time.time()

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
            'time': int(self._now()),
            'mp_lib': 'python',
            '$lib_version': VERSION,
        }
        all_properties.update(properties)
        event = {
            'event': event_name,
            'properties': all_properties,
        }
        self._consumer.send('events', json.dumps(event))

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
        return self.people_update({
            '$distinct_id': distinct_id,
            '$set': properties,
        })

    def people_set_once(self, distinct_id, properties):
        """
        Set immutable properties of a people record.

        Sets properties of a people record given in JSON object. If the profile
        does not exist, creates new profile with these properties. Does not
        overwrite existing property values.
        Example:
            mp.people_set_once('12345', {'First Login': "2013-04-01T13:20:00"})
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$set_once': properties,
        })

    def people_increment(self, distinct_id, properties):
        """
        Increments/decrements numerical properties of people record.

        Takes in JSON object with keys and numerical values. Adds numerical
        values to current property of profile. If property doesn't exist adds
        value to zero. Takes in negative values for subtraction.
        Example:
            mp.people_add('12345', {'Coins Gathered': 12})
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$add': properties,
        })

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
        return self.people_update({
            '$distinct_id': distinct_id,
            '$append': properties,
        })

    def people_union(self, distinct_id, properties):
        """
        Merges the values for a list associated with a property.

        Takes a JSON object containing keys and list values. The list values in
        the request are merged with the existing list on the user profile,
        ignoring duplicate list values.
        Example:
            mp.people_union('12345', { "Items purchased": ["socks", "shirts"] } )
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$union': properties,
        })

    def people_unset(self, distinct_id, properties):
        """
        Removes properties from a profile.

        Takes a JSON list of string property names, and permanently removes the
        properties and their values from a profile.
        Example:
            mp.people_unset('12345', ["Days Overdue"])
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$unset': properties,
        })

    def people_delete(self, distinct_id):
        """
        Permanently deletes a profile.

        Permanently delete the profile from Mixpanel, along with all of its
        properties.
        Example:
            mp.people_delete('12345')
        """
        return self.people_update({
            '$distinct_id': distinct_id,
            '$delete': "",
        })

    def people_track_charge(self, distinct_id, amount, properties={}):
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


    """
    Send a generic update to \Mixpanel people analytics.
    Caller is responsible for formatting the update message, as
    documented in the \Mixpanel HTTP specification, and passing
    the message as a dict to update. This
    method might be useful if you want to use very new
    or experimental features of people analytics from Ruby
    The \Mixpanel HTTP tracking API is documented at
    https://mixpanel.com/help/reference/http
    """
    def people_update(self, message):
        record = {
            '$token': self._token,
            '$time': int(self._now() * 1000),
        }
        record.update(message)
        self._consumer.send('people', json.dumps(record))
