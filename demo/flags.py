#import sys
import os
#sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import mixpanel

if __name__ == '__main__':
    mp = mixpanel.Mixpanel("391d3916270285cbf9f433f51a99a44c")
    
    # Example 1: Local flags (with flag definitions fetched and cached locally)
    print("=== LOCAL FLAGS EXAMPLE ===")
    local_config = mixpanel.LocalFlagsConfig(api_host="api.mixpanel.com")
    local_flags_provider = mp.getLocalFlagsProvider(local_config)

    user_context = {
        "distinct_id": "test-user-1"
    }

    local_variant = local_flags_provider.get_variant("funnel_reentry", "control", user_context)
    print("LOCAL VARIANT IS ", local_variant)

    # Example 2: Remote flags (flags evaluated remotely on each call)
    print("\n=== REMOTE FLAGS EXAMPLE ===")
    remote_config = mixpanel.RemoteFlagsConfig(api_host="api.mixpanel.com")
    remote_flags_provider = mp.getRemoteFlagsProvider(remote_config)

    import asyncio
    async def test_remote_flags():
        async with remote_flags_provider:
            remote_variant = await remote_flags_provider.get_variant("funnel_reentry", "control", user_context)
            print("REMOTE VARIANT (async) IS ", remote_variant)

    asyncio.run(test_remote_flags())

    # Using sync version
    remote_variant_sync = remote_flags_provider.get_variant_sync("funnel_reentry", "control", user_context)
    print("REMOTE VARIANT (sync) IS ", remote_variant_sync)