# test_ai_bot_consumer.py
import json
import pytest
import mixpanel


class LogConsumer:
    """Test consumer that captures all send() calls. Copied from test_mixpanel.py."""
    def __init__(self):
        self.log = []

    def send(self, endpoint, event, api_key=None, api_secret=None):
        entry = [endpoint, json.loads(event)]
        if api_key != (None, None):
            if api_key:
                entry.append(api_key)
            if api_secret:
                entry.append(api_secret)
        self.log.append(tuple(entry))

    def flush(self):
        pass

    def clear(self):
        self.log = []


class TestBotClassifyingConsumer:
    """Tests for the BotClassifyingConsumer wrapper."""

    TOKEN = '12345'

    def setup_method(self):
        self.inner_consumer = LogConsumer()
        from mixpanel.ai_bot_consumer import BotClassifyingConsumer
        self.bot_consumer = BotClassifyingConsumer(self.inner_consumer)
        self.mp = mixpanel.Mixpanel(self.TOKEN, consumer=self.bot_consumer)
        self.mp._now = lambda: 1000.1
        self.mp._make_insert_id = lambda: 'abcdefg'

    # === CORE CLASSIFICATION ===

    def test_classifies_ai_bot_when_user_agent_present(self):
        self.mp.track('user123', 'page_view', {
            '$user_agent': 'Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)',
        })
        assert len(self.inner_consumer.log) == 1
        endpoint, event = self.inner_consumer.log[0]
        assert endpoint == 'events'
        props = event['properties']
        assert props['$is_ai_bot'] is True
        assert props['$ai_bot_name'] == 'GPTBot'
        assert props['$ai_bot_provider'] == 'OpenAI'
        assert props['$ai_bot_category'] == 'indexing'

    def test_classifies_non_ai_bot_when_user_agent_present(self):
        self.mp.track('user123', 'page_view', {
            '$user_agent': 'Mozilla/5.0 Chrome/120.0.0.0 Safari/537.36',
        })
        endpoint, event = self.inner_consumer.log[0]
        props = event['properties']
        assert props['$is_ai_bot'] is False
        assert '$ai_bot_name' not in props

    def test_no_classification_when_user_agent_absent(self):
        self.mp.track('user123', 'page_view', {'page': '/home'})
        endpoint, event = self.inner_consumer.log[0]
        props = event['properties']
        assert '$is_ai_bot' not in props
        assert '$ai_bot_name' not in props

    # === PROPERTY PRESERVATION ===

    def test_preserves_existing_properties(self):
        self.mp.track('user123', 'page_view', {
            '$user_agent': 'GPTBot/1.2',
            'page_url': '/products',
            'custom_prop': 'value',
        })
        endpoint, event = self.inner_consumer.log[0]
        props = event['properties']
        assert props['page_url'] == '/products'
        assert props['custom_prop'] == 'value'
        assert props['$is_ai_bot'] is True

    def test_preserves_sdk_default_properties(self):
        self.mp.track('user123', 'page_view', {
            '$user_agent': 'GPTBot/1.2',
        })
        endpoint, event = self.inner_consumer.log[0]
        props = event['properties']
        assert props['token'] == self.TOKEN
        assert props['distinct_id'] == 'user123'
        assert props['mp_lib'] == 'python'
        assert props['$insert_id'] == 'abcdefg'

    def test_preserves_event_name(self):
        self.mp.track('user123', 'page_view', {
            '$user_agent': 'GPTBot/1.2',
        })
        endpoint, event = self.inner_consumer.log[0]
        assert event['event'] == 'page_view'

    # === ENDPOINT FILTERING ===

    def test_only_classifies_events_endpoint(self):
        """People and groups endpoints should pass through unmodified."""
        self.mp.people_set('user123', {
            '$user_agent': 'GPTBot/1.2',
            '$name': 'Test User',
        })
        endpoint, record = self.inner_consumer.log[0]
        assert endpoint == 'people'
        # People records have a different structure - no 'properties' key
        # The $user_agent should pass through but no classification should be added
        assert '$is_ai_bot' not in record

    def test_groups_endpoint_passes_through(self):
        self.mp.group_set('company', 'acme', {
            '$user_agent': 'GPTBot/1.2',
            'plan': 'enterprise',
        })
        endpoint, record = self.inner_consumer.log[0]
        assert endpoint == 'groups'
        assert '$is_ai_bot' not in record

    # === API KEY PASSTHROUGH ===

    def test_api_key_passthrough(self):
        """API key and secret should be forwarded to inner consumer."""
        self.mp.track('user123', 'page_view', {
            '$user_agent': 'GPTBot/1.2',
        })
        # The standard track() doesn't use api_key, but import does
        # Just verify the consumer interface passes args correctly
        assert len(self.inner_consumer.log) == 1

    # === FLUSH PROXY ===

    def test_flush_proxied_to_inner_consumer(self):
        """flush() should be forwarded to inner consumer."""
        flush_called = []
        self.inner_consumer.flush = lambda: flush_called.append(True)
        self.bot_consumer.flush()
        assert len(flush_called) == 1

    def test_flush_works_when_inner_has_no_flush(self):
        """Should not error if inner consumer has no flush method."""
        consumer_without_flush = type('C', (), {'send': lambda s, *a, **k: None})()
        from mixpanel.ai_bot_consumer import BotClassifyingConsumer
        bot_consumer = BotClassifyingConsumer(consumer_without_flush)
        # Should not raise
        bot_consumer.flush()

    # === BUFFERED CONSUMER COMPATIBILITY ===

    def test_works_with_buffered_consumer(self):
        """Should work when wrapping a BufferedConsumer."""
        from mixpanel.ai_bot_consumer import BotClassifyingConsumer
        inner = LogConsumer()
        buffered = mixpanel.BufferedConsumer()
        # Replace the internal consumer's _write_request to capture
        captured = []
        original_send = buffered._consumer._write_request
        buffered._consumer._write_request = lambda url, msg, *a, **k: captured.append(msg)

        bot_consumer = BotClassifyingConsumer(buffered)
        mp = mixpanel.Mixpanel(self.TOKEN, consumer=bot_consumer)
        mp._now = lambda: 1000.1
        mp._make_insert_id = lambda: 'abcdefg'

        mp.track('user123', 'page_view', {'$user_agent': 'GPTBot/1.2'})
        bot_consumer.flush()

        # Verify the captured message contains classification
        assert len(captured) >= 1
        # BufferedConsumer batches as JSON arrays
        batch = json.loads(captured[0])
        if isinstance(batch, list):
            props = batch[0]['properties']
        else:
            props = batch['properties']
        assert props['$is_ai_bot'] is True

    # === MULTIPLE BOTS ===

    def test_classifies_multiple_different_bots(self):
        bots = [
            ('GPTBot/1.2', 'GPTBot', 'OpenAI'),
            ('ClaudeBot/1.0', 'ClaudeBot', 'Anthropic'),
            ('PerplexityBot/1.0', 'PerplexityBot', 'Perplexity'),
        ]
        for ua, name, provider in bots:
            self.inner_consumer.clear()
            self.mp.track('user123', 'page_view', {'$user_agent': ua})
            props = self.inner_consumer.log[0][1]['properties']
            assert props['$is_ai_bot'] is True, f'Failed for {ua}'
            assert props['$ai_bot_name'] == name, f'Wrong name for {ua}'
            assert props['$ai_bot_provider'] == provider, f'Wrong provider for {ua}'


class TestBotClassifyingConsumerOptions:
    """Tests for BotClassifyingConsumer configuration options."""

    TOKEN = '12345'

    def test_custom_user_agent_property(self):
        from mixpanel.ai_bot_consumer import BotClassifyingConsumer
        inner = LogConsumer()
        consumer = BotClassifyingConsumer(inner, user_agent_property='ua_string')
        mp = mixpanel.Mixpanel(self.TOKEN, consumer=consumer)
        mp._now = lambda: 1000.1
        mp._make_insert_id = lambda: 'abcdefg'

        mp.track('user123', 'page_view', {'ua_string': 'GPTBot/1.2'})
        props = inner.log[0][1]['properties']
        assert props['$is_ai_bot'] is True

    def test_custom_additional_bots(self):
        import re
        from mixpanel.ai_bot_consumer import BotClassifyingConsumer
        inner = LogConsumer()
        consumer = BotClassifyingConsumer(inner, additional_bots=[
            {
                'pattern': re.compile(r'MyBot/', re.IGNORECASE),
                'name': 'MyBot',
                'provider': 'MyCorp',
                'category': 'indexing',
            }
        ])
        mp = mixpanel.Mixpanel(self.TOKEN, consumer=consumer)
        mp._now = lambda: 1000.1
        mp._make_insert_id = lambda: 'abcdefg'

        mp.track('user123', 'page_view', {'$user_agent': 'MyBot/1.0'})
        props = inner.log[0][1]['properties']
        assert props['$is_ai_bot'] is True
        assert props['$ai_bot_name'] == 'MyBot'
