import os
import asyncio
import mixpanel
import logging

logging.basicConfig(level=logging.INFO)

# Configure your project token, the feature flag  to test, and user context to evaluate.
PROJECT_TOKEN = "044781e247eabd8e9b73fad8a8c093d2"
FLAG_KEY = "sample-flag"
FLAG_FALLBACK_VARIANT = "control"
USER_CONTEXT = { "distinct_id": "sample-distinct-id" }

# If False, the flag definitions are fetched just once on SDK initialization. Otherwise, will poll
SHOULD_POLL_CONTINOUSLY = False
POLLING_INTERVAL_IN_SECONDS = 90

# Use the correct data residency endpoint for your project.
API_HOST = "api-eu.mixpanel.com"

async def main():
    mp = mixpanel.Mixpanel(PROJECT_TOKEN)
    local_config = mixpanel.LocalFlagsConfig(api_host=API_HOST, enable_polling=SHOULD_POLL_CONTINOUSLY, polling_interval_in_seconds=POLLING_INTERVAL_IN_SECONDS)

    async with mp.get_local_flags_provider(local_config) as local_flags_provider:
        await local_flags_provider.astart_polling_for_definitions()

        variant_value = local_flags_provider.get_variant_value(FLAG_KEY, FLAG_FALLBACK_VARIANT, USER_CONTEXT)
        print(f"Variant value: {variant_value}")

if __name__ == '__main__':
    asyncio.run(main())