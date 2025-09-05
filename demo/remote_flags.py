import asyncio
import mixpanel
import logging

logging.basicConfig(level=logging.INFO)

# Configure your project token, the feature flag to test, and user context to evaluate.
PROJECT_TOKEN = ""
FLAG_KEY = "sample-flag"
FLAG_FALLBACK_VARIANT = "control"
USER_CONTEXT = { "distinct_id": "sample-distinct-id" }

# Use the correct data residency endpoint for your project.
API_HOST = "api-eu.mixpanel.com"

DEMO_ASYNC = True

async def async_demo():
    remote_config = mixpanel.RemoteFlagsConfig(api_host=API_HOST)
    # Optionally use mixpanel client as a context manager, that will ensure shutdown of resources used by feature flagging
    async with mixpanel.Mixpanel(PROJECT_TOKEN, remote_flags_config=remote_config) as mp:
        variant_value = await mp.remote_flags.aget_variant_value(FLAG_KEY, FLAG_FALLBACK_VARIANT, USER_CONTEXT)
        print(f"Variant value: {variant_value}")

def sync_demo():
    remote_config = mixpanel.RemoteFlagsConfig(api_host=API_HOST)
    with mixpanel.Mixpanel(PROJECT_TOKEN, remote_flags_config=remote_config) as mp:
        variant_value = mp.remote_flags.get_variant_value(FLAG_KEY, FLAG_FALLBACK_VARIANT, USER_CONTEXT)
        print(f"Variant value: {variant_value}")

if __name__ == '__main__':
    if DEMO_ASYNC:
        asyncio.run(async_demo())
    else:
        sync_demo()