===============
mixpanel-python
===============

This is the official Mixpanel Python library. This library allows for server-side intergration of Mixpanel.

Installation
============

The library can be installed using pip::
    pip install mixpanel-python

Getting Started
===============

Typical usage usually looks like this::
    #!/usr/bin/env python
    from mixpanel import Mixpanel

    mp = Mixpanel(YOUR_TOKEN)

    # tracks an event with certain properties
    mp.track('button clicked', {'color' : 'blue', 'size': 'large'})

    # sends an update to a user profile
    mp.people_set(USER_ID, {'$first_name' : 'Amy', 'favorite color': 'red'})

You can use an instance of the Mixpanel class for sending all of your events and people updates.

Additional Information
======================

For more information please visit:

* Our Ruby API Integration page[https://mixpanel.com/help/reference/python]
* The documentation[http://mixpanel.github.io/mixpanel-python]
