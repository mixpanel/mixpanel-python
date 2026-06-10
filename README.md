# mixpanel-python

##### _May 13, 2026_ - [v5.1.0](https://github.com/mixpanel/mixpanel-python/releases/tag/v5.1.0)

[![PyPI](https://img.shields.io/pypi/v/mixpanel)](https://pypi.org/project/mixpanel)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/mixpanel)](https://pypi.org/project/mixpanel)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/mixpanel)](https://pypi.org/project/mixpanel)
![Tests](https://github.com/mixpanel/mixpanel-python/workflows/Tests/badge.svg)

This is the official Mixpanel Python library. This library allows for
server-side integration of Mixpanel.

To import, export, transform, or delete your Mixpanel data, please see our
[mixpanel-utils package](https://github.com/mixpanel/mixpanel-utils).

## Installation

The library can be installed using pip:

```bash
pip install mixpanel
```

## Getting Started

Typical usage usually looks like this:

```python
from mixpanel import Mixpanel

mp = Mixpanel(YOUR_TOKEN)

# tracks an event with certain properties
mp.track(DISTINCT_ID, 'button clicked', {'color' : 'blue', 'size': 'large'})

# sends an update to a user profile
mp.people_set(DISTINCT_ID, {'$first_name' : 'Ilya', 'favorite pizza': 'margherita'})
```

You can use an instance of the Mixpanel class for sending all of your events
and people updates.

## Service Account Authentication

For enhanced security in server-to-server integrations, you can use service account credentials instead of API tokens:

```python
from mixpanel import Mixpanel

mp = Mixpanel(
    YOUR_TOKEN,
    service_account_username='YOUR_SERVICE_ACCOUNT_USERNAME',
    service_account_secret='YOUR_SERVICE_ACCOUNT_SECRET'
)

# All API calls will use service account authentication
mp.track(DISTINCT_ID, 'button clicked', {'color': 'blue'})
mp.people_set(DISTINCT_ID, {'$first_name': 'John'})
```

Service account credentials can also be used with `Consumer` and `BufferedConsumer`:

```python
from mixpanel import Mixpanel, BufferedConsumer

consumer = BufferedConsumer(
    service_account_username='YOUR_SERVICE_ACCOUNT_USERNAME',
    service_account_secret='YOUR_SERVICE_ACCOUNT_SECRET'
)

mp = Mixpanel(YOUR_TOKEN, consumer=consumer)
```

When service account credentials are provided, they take precedence over API secrets for authentication.

## Additional Information

* [Help Docs](https://www.mixpanel.com/help/reference/python)
* [Full Documentation](http://mixpanel.github.io/mixpanel-python/)
* [mixpanel-python-async](https://github.com/jessepollak/mixpanel-python-async); a third party tool for sending data asynchronously
from the tracking python process.

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/mixpanel/mixpanel-python)
