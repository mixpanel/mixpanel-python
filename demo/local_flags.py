import os
import asyncio
import mixpanel

async def main():
    mp = mixpanel.Mixpanel("391d3916270285cbf9f433f51a99a44c")
    
    print("=== LOCAL FLAGS EXAMPLE ===")
    
    local_config = mixpanel.LocalFlagsConfig()
    local_config.api_host = "api.mixpanel.com"
    local_config.enablePolling = True
    local_config.pollingIntervalInSeconds = 60

    async with mp.getLocalFlagsProvider(local_config) as local_flags_provider:
        await local_flags_provider.start_polling_for_definitions()

        user_context = {
            "distinct_id": "test-user-1"
        }

        variant_value = local_flags_provider.get_variant_value("test-flag", "control", user_context)
        print(f"Variant value: {variant_value}")

        variant = local_flags_provider.get_variant("test-flag", 
                                                  mixpanel.SelectedVariant(variant_key="control", variant_value="control"), 
                                                  user_context)

        print(f"Full variant: key={variant.variant_key}, value={variant.variant_value}")
        
        is_enabled = local_flags_provider.is_enabled("funnel_reentry", user_context)
        print(f"Feature enabled: {is_enabled}")

if __name__ == '__main__':
    asyncio.run(main())