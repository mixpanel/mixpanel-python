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

async def async_demo(remote_config):
    async with mp.get_remote_flags_provider(remote_config) as remote_flags_provider:
        variant_value = await remote_flags_provider.aget_variant_value(FLAG_KEY, FLAG_FALLBACK_VARIANT, USER_CONTEXT)
        print(f"Variant value: {variant_value}")

def sync_demo(remote_config):
    with mp.get_remote_flags_provider(remote_config) as remote_flags_provider:
        variant_value = remote_flags_provider.get_variant_value(FLAG_KEY, FLAG_FALLBACK_VARIANT, USER_CONTEXT)
        print(f"Variant value: {variant_value}")

if __name__ == '__main__':
    mp = mixpanel.Mixpanel(PROJECT_TOKEN)
    remote_config = mixpanel.RemoteFlagsConfig(api_host=API_HOST)

    if DEMO_ASYNC:
        asyncio.run(async_demo(remote_config))
    else:
        sync_demo(remote_config)