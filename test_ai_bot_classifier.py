# test_ai_bot_classifier.py
import pytest


class TestClassifyUserAgent:
    """Tests for the core user-agent classification function."""

    def setup_method(self):
        from mixpanel.ai_bot_classifier import classify_user_agent
        self.classify = classify_user_agent

    # === OpenAI Bots ===

    def test_classifies_gptbot(self):
        result = self.classify(
            'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; '
            'GPTBot/1.2; +https://openai.com/gptbot)'
        )
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'GPTBot'
        assert result['$ai_bot_provider'] == 'OpenAI'
        assert result['$ai_bot_category'] == 'indexing'

    def test_classifies_chatgpt_user(self):
        result = self.classify(
            'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; '
            'ChatGPT-User/1.0; +https://openai.com/bot)'
        )
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'ChatGPT-User'
        assert result['$ai_bot_provider'] == 'OpenAI'
        assert result['$ai_bot_category'] == 'retrieval'

    def test_classifies_oai_searchbot(self):
        result = self.classify(
            'Mozilla/5.0 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)'
        )
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'OAI-SearchBot'
        assert result['$ai_bot_provider'] == 'OpenAI'
        assert result['$ai_bot_category'] == 'indexing'

    # === Anthropic Bots ===

    def test_classifies_claudebot(self):
        result = self.classify(
            'Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)'
        )
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'ClaudeBot'
        assert result['$ai_bot_provider'] == 'Anthropic'
        assert result['$ai_bot_category'] == 'indexing'

    def test_classifies_claude_user(self):
        result = self.classify('Mozilla/5.0 (compatible; Claude-User/1.0)')
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'Claude-User'
        assert result['$ai_bot_provider'] == 'Anthropic'
        assert result['$ai_bot_category'] == 'retrieval'

    # === Google Bots ===

    def test_classifies_google_extended(self):
        result = self.classify('Mozilla/5.0 (compatible; Google-Extended/1.0)')
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'Google-Extended'
        assert result['$ai_bot_provider'] == 'Google'
        assert result['$ai_bot_category'] == 'indexing'

    # === Perplexity ===

    def test_classifies_perplexitybot(self):
        result = self.classify('Mozilla/5.0 (compatible; PerplexityBot/1.0)')
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'PerplexityBot'
        assert result['$ai_bot_provider'] == 'Perplexity'
        assert result['$ai_bot_category'] == 'retrieval'

    # === ByteDance ===

    def test_classifies_bytespider(self):
        result = self.classify('Mozilla/5.0 (compatible; Bytespider/1.0)')
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'Bytespider'
        assert result['$ai_bot_provider'] == 'ByteDance'
        assert result['$ai_bot_category'] == 'indexing'

    # === Common Crawl ===

    def test_classifies_ccbot(self):
        result = self.classify('CCBot/2.0 (https://commoncrawl.org/faq/)')
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'CCBot'
        assert result['$ai_bot_provider'] == 'Common Crawl'
        assert result['$ai_bot_category'] == 'indexing'

    # === Apple ===

    def test_classifies_applebot_extended(self):
        result = self.classify(
            'Mozilla/5.0 (Macintosh; Intel Mac OS X) '
            'AppleWebKit/605.1.15 (KHTML, like Gecko) Applebot-Extended/0.1'
        )
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'Applebot-Extended'
        assert result['$ai_bot_provider'] == 'Apple'
        assert result['$ai_bot_category'] == 'indexing'

    # === Meta ===

    def test_classifies_meta_external_agent(self):
        result = self.classify('Mozilla/5.0 (compatible; Meta-ExternalAgent/1.0)')
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'Meta-ExternalAgent'
        assert result['$ai_bot_provider'] == 'Meta'
        assert result['$ai_bot_category'] == 'indexing'

    # === Cohere ===

    def test_classifies_cohere_ai(self):
        result = self.classify('cohere-ai/1.0 (https://cohere.com)')
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'cohere-ai'
        assert result['$ai_bot_provider'] == 'Cohere'
        assert result['$ai_bot_category'] == 'indexing'

    # === NEGATIVE CASES ===

    def test_not_ai_bot_chrome(self):
        result = self.classify(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        assert result['$is_ai_bot'] is False
        assert '$ai_bot_name' not in result

    def test_not_ai_bot_googlebot_regular(self):
        result = self.classify(
            'Mozilla/5.0 (compatible; Googlebot/2.1; '
            '+http://www.google.com/bot.html)'
        )
        assert result['$is_ai_bot'] is False

    def test_not_ai_bot_bingbot_regular(self):
        result = self.classify(
            'Mozilla/5.0 (compatible; bingbot/2.0; '
            '+http://www.bing.com/bingbot.htm)'
        )
        assert result['$is_ai_bot'] is False

    def test_not_ai_bot_curl(self):
        result = self.classify('curl/7.64.1')
        assert result['$is_ai_bot'] is False

    def test_empty_user_agent(self):
        result = self.classify('')
        assert result['$is_ai_bot'] is False

    def test_none_user_agent(self):
        result = self.classify(None)
        assert result['$is_ai_bot'] is False

    # === CASE SENSITIVITY ===

    def test_case_insensitive_matching(self):
        result = self.classify('mozilla/5.0 (compatible; gptbot/1.2)')
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'GPTBot'

    # === RETURN SHAPE ===

    def test_match_returns_all_fields(self):
        result = self.classify('GPTBot/1.2')
        assert '$is_ai_bot' in result
        assert '$ai_bot_name' in result
        assert '$ai_bot_provider' in result
        assert '$ai_bot_category' in result
        assert result['$ai_bot_category'] in ('indexing', 'retrieval', 'agent')

    def test_no_match_returns_only_is_ai_bot(self):
        result = self.classify('Chrome/120')
        assert list(result.keys()) == ['$is_ai_bot']
        assert result['$is_ai_bot'] is False


class TestGetBotDatabase:
    """Tests for the bot database accessor."""

    def test_returns_list(self):
        from mixpanel.ai_bot_classifier import get_bot_database
        db = get_bot_database()
        assert isinstance(db, list)
        assert len(db) > 0

    def test_entries_have_required_fields(self):
        from mixpanel.ai_bot_classifier import get_bot_database
        db = get_bot_database()
        for entry in db:
            assert 'name' in entry
            assert 'provider' in entry
            assert 'category' in entry
            assert entry['category'] in ('indexing', 'retrieval', 'agent')


class TestCreateClassifier:
    """Tests for custom classifier creation."""

    def test_additional_bots_are_checked(self):
        from mixpanel.ai_bot_classifier import create_classifier
        import re

        classifier = create_classifier(additional_bots=[
            {
                'pattern': re.compile(r'MyCustomBot/', re.IGNORECASE),
                'name': 'MyCustomBot',
                'provider': 'CustomCorp',
                'category': 'indexing',
            }
        ])
        result = classifier('Mozilla/5.0 (compatible; MyCustomBot/1.0)')
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'MyCustomBot'

    def test_additional_bots_take_priority(self):
        from mixpanel.ai_bot_classifier import create_classifier
        import re

        classifier = create_classifier(additional_bots=[
            {
                'pattern': re.compile(r'GPTBot/', re.IGNORECASE),
                'name': 'GPTBot-Custom',
                'provider': 'CustomProvider',
                'category': 'retrieval',
            }
        ])
        result = classifier('GPTBot/1.2')
        assert result['$ai_bot_name'] == 'GPTBot-Custom'

    def test_built_in_bots_still_work(self):
        from mixpanel.ai_bot_classifier import create_classifier

        classifier = create_classifier(additional_bots=[])
        result = classifier('ClaudeBot/1.0')
        assert result['$is_ai_bot'] is True
        assert result['$ai_bot_name'] == 'ClaudeBot'
