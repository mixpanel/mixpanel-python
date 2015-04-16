mixpanel-python |travis-badge|
==============================

This is the official Mixpanel Python library. This library allows for
server-side integration of Mixpanel.


Installation
------------

The library can be installed using pip::

    pip install mixpanel


Getting Started
---------------

Typical usage usually looks like this::

    from mixpanel import Mixpanel

    mp = Mixpanel(YOUR_TOKEN)

    # tracks an event with certain properties
    mp.track(USER_ID, 'button clicked', {'color' : 'blue', 'size': 'large'})

    # sends an update to a user profile
    mp.people_set(USER_ID, {'$first_name' : 'Amy', 'favorite color': 'red'})

You can use an instance of the Mixpanel class for sending all of your events
and people updates.


Additional Information
----------------------

* `Help Docs`_
* `Full Documentation`_
* mixpanel-python-async_; a third party tool for sending data asynchronously
  from the tracking python process.
* mixpanel-py3_; a fork of this library that supports Python 3, and some
  additional features, maintained by Fredrik Svensson.


.. |travis-badge| image:: https://travis-ci.org/mixpanel/mixpanel-python.svg?branch=master
    :target: https://travis-ci.org/mixpanel/mixpanel-python
.. _Help Docs: https://www.mixpanel.com/help/reference/python
.. _Full Documentation: http://mixpanel.github.io/mixpanel-python/
.. _mixpanel-python-async: https://github.com/jessepollak/mixpanel-python-async
.. _mixpanel-py3: https://github.com/MyGGaN/mixpanel-python
