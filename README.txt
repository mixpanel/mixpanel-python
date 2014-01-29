mixpanel-python
===============
This is the official Mixpanel Python library. This library allows for server-side integration of Mixpanel.

Installation
------------
The library can be installed using pip:

    pip install mixpanel-py

Getting Started
---------------
Typical usage usually looks like this:

    #!/usr/bin/env python
    from mixpanel import Mixpanel

    mp = Mixpanel(YOUR_TOKEN)

    # tracks an event with certain properties
    mp.track('button clicked', {'color' : 'blue', 'size': 'large'})

    # sends an update to a user profile
    mp.people_set(USER_ID, {'$first_name' : 'Amy', 'favorite color': 'red'})

You can use an instance of the Mixpanel class for sending all of your events and people updates.

Additional Information
----------------------
[Help Docs](https://www.mixpanel.com/help/reference/python)

[Full Documentation](http://mixpanel.github.io/mixpanel-python/)

[mixpanel-python-asyc](https://github.com/jessepollak/mixpanel-python-async) a third party tool for sending data asynchronously from the tracking python process.
