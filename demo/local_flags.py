import os
import asyncio
import mixpanel
import logging

logging.basicConfig(level=logging.INFO)

# Configure your project token, the feature flag  to test, and user context to evaluate.
PROJECT_TOKEN = ""
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
    local_config = mixpanel.LocalFlagsConfig(api_host=API_HOST, enablePolling=SHOULD_POLL_CONTINOUSLY, pollingIntervalInSeconds=POLLING_INTERVAL_IN_SECONDS)

    async with mp.getLocalFlagsProvider(local_config) as local_flags_provider:
        await local_flags_provider.start_polling_for_definitions()

        variant_value = local_flags_provider.get_variant_value(FLAG_KEY, FLAG_FALLBACK_VARIANT, USER_CONTEXT)
        print(f"Variant value: {variant_value}")

if __name__ == '__main__':
    asyncio.run(main())