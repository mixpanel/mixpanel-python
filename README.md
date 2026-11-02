# mixpanel-python

##### _September 03, 2026_ - [v5.4.1](https://github.com/mixpanel/mixpanel-python/releases/tag/v5.4.1)

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

## Hierarchical Groups

If your project uses hierarchical groups, create the client with
`hierarchical_groups=True` and identify users with a `MixpanelIdentity`, which
sends `$user_id` and `$company_id` so Mixpanel can build the distinct id:

```python
from mixpanel import Mixpanel, MixpanelIdentity

mp = Mixpanel(YOUR_TOKEN, hierarchical_groups=True)
user = MixpanelIdentity(user_id='user_123', company_id='acme')

mp.track(user, 'Signup', {'plan': 'enterprise'})
mp.track(MixpanelIdentity(device_id='device_abc'), 'Page View')  # anonymous

# User profiles are group profiles keyed by $user_id within the company
mp.people_set(user, {'role': 'admin'})

# Group profile updates need a company: bind one with for_company()
acme = mp.for_company('acme')
acme.group_set('$company_id', 'acme', {'tier': 'enterprise'})
acme.group_set('department', 'finance', {'budget': 100000})
```

On a hierarchical groups project, user profiles support `people_set`,
`people_set_once`, `people_unset`, `people_union`, `people_remove` and
`people_delete`; `people_increment`, `people_append` and `people_track_charge`
raise `UnsupportedOperationError`. Group profile updates without a company
raise `CompanyRequiredError`. A `$user_id` sent without a `$company_id` (and
without a `$device_id`) names a separate user, so it raises `ValueError`.

User profile updates on a hierarchical groups project never go to `/engage`.
A distinct id of the form `$company:{company}|$user:{user}` is sent to
`/groups` as that company and user, the same update a
`MixpanelIdentity(user_id=user, company_id=company)` sends; any other distinct
id raises `ValueError` and nothing is sent. Events are unaffected: a distinct
id passed to `track` or `import_data` is sent as is.

```python
mp.people_set('$company:acme|$user:user_123', {'role': 'admin'})  # /groups
mp.people_set('user_123', {'role': 'admin'})  # raises ValueError
```

## Service Account Authentication

For enhanced security in server-to-server integrations, you can use service account credentials for authentication instead of API secrets:

```python
from mixpanel import Mixpanel, ServiceAccountCredentials

# Create credentials object
# Service accounts replace api_key/api_secret for authentication
credentials = ServiceAccountCredentials(
    username='YOUR_SERVICE_ACCOUNT_USERNAME',
    secret='YOUR_SERVICE_ACCOUNT_SECRET',
    project_id='YOUR_PROJECT_ID'
)

# Token identifies the project and is used for event tracking
# Credentials are used for endpoints that require authentication
mp = Mixpanel(YOUR_TOKEN, credentials=credentials)

# Event tracking operations use the token (sent in payload)
mp.track(DISTINCT_ID, 'button clicked', {'color': 'blue'})
mp.people_set(DISTINCT_ID, {'$first_name': 'John'})
```

Service account credentials can also be used with custom consumers like `BufferedConsumer`:

```python
from mixpanel import Mixpanel, BufferedConsumer, ServiceAccountCredentials

credentials = ServiceAccountCredentials(
    username='YOUR_SERVICE_ACCOUNT_USERNAME',
    secret='YOUR_SERVICE_ACCOUNT_SECRET',
    project_id='YOUR_PROJECT_ID'
)

# Option 1: Pass credentials to the consumer constructor
consumer = BufferedConsumer(max_size=50, credentials=credentials)
mp = Mixpanel(YOUR_TOKEN, consumer=consumer)

# Option 2: Let Mixpanel create the default consumer with credentials
mp = Mixpanel(YOUR_TOKEN, credentials=credentials)

# Event tracking uses the token (sent in payload)
mp.track(DISTINCT_ID, 'event_name')
```

Service account credentials are only used for the `/import` endpoint and feature flags. Regular event tracking operations (`track`, `people_set`, `group_set`) use the token provided in the constructor, which is sent in the event payload.

### Service Accounts with Feature Flags

Service account credentials are automatically used for feature flag operations when configured:

```python
from mixpanel import Mixpanel, ServiceAccountCredentials
from mixpanel.flags.types import LocalFlagsConfig

credentials = ServiceAccountCredentials(
    username='YOUR_SERVICE_ACCOUNT_USERNAME',
    secret='YOUR_SERVICE_ACCOUNT_SECRET',
    project_id='YOUR_PROJECT_ID'
)

# Token identifies the project for event tracking, credentials handle authentication
mp = Mixpanel(
    YOUR_TOKEN,
    credentials=credentials,
    local_flags_config=LocalFlagsConfig()
)

# Feature flag requests will use service account authentication
variant = mp.local_flags.get_variant_value('my-flag', fallback_value=False, context={...})
```

**Note**: When using service account credentials, the `token` parameter in the `Mixpanel` constructor is still required for event tracking operations (`track`, `people_set`, etc.) since the token is included in the event data payload. However, feature flag operations use the `project_id` from credentials instead of the token for authentication.

## Additional Information

* [Help Docs](https://www.mixpanel.com/help/reference/python)
* [Full Documentation](http://mixpanel.github.io/mixpanel-python/)
* [mixpanel-python-async](https://github.com/jessepollak/mixpanel-python-async); a third party tool for sending data asynchronously
from the tracking python process.

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/mixpanel/mixpanel-python)
