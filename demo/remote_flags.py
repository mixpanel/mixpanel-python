import asyncio
import mixpanel

async def main():
    mp = mixpanel.Mixpanel("391d3916270285cbf9f433f51a99a44c")
    remote_config = mixpanel.RemoteFlagsConfig()
    remote_flags_provider = mp.getRemoteFlagsProvider(remote_config)
    user_context = {
        "distinct_id": "test-user-1"
    }
    
    print("=== ASYNC VERSION ===")
    async with remote_flags_provider:
        variant_value = await remote_flags_provider.get_variant_value("sample-flag", "control", user_context)
        print(f"Async variant value: {variant_value}")
        
        variant = await remote_flags_provider.get_variant("sample-flag", 
                                                         mixpanel.SelectedVariant(variant_key="control", variant_value="control"), 
                                                         user_context)
        print(f"Async full variant: key={variant.variant_key}, value={variant.variant_value}")
        
        is_enabled = await remote_flags_provider.is_enabled("sample-flag", user_context)
        print(f"Async feature enabled: {is_enabled}")
    
    print("\n=== SYNC VERSION ===")
    variant_value_sync = remote_flags_provider.get_variant_value_sync("sample-flag", "control", user_context)
    print(f"Sync variant value: {variant_value_sync}")
    
    variant_sync = remote_flags_provider.get_variant_sync("sample-flag", 
                                                         mixpanel.SelectedVariant(variant_key="control", variant_value="control"), 
                                                         user_context)
    print(f"Sync full variant: key={variant_sync.variant_key}, value={variant_sync.variant_value}")
    
    is_enabled_sync = remote_flags_provider.is_enabled_sync("sample-flag", user_context)
    print(f"Sync feature enabled: {is_enabled_sync}")

if __name__ == '__main__':
    asyncio.run(main())