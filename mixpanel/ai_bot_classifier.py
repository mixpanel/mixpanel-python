# mixpanel/ai_bot_classifier.py
"""AI bot user-agent classification for Mixpanel events."""

import re
from typing import Any, Callable, Dict, List, Optional

AI_BOT_DATABASE: List[Dict[str, Any]] = [
    {
        'pattern': re.compile(r'GPTBot/', re.IGNORECASE),
        'name': 'GPTBot',
        'provider': 'OpenAI',
        'category': 'indexing',
        'description': 'OpenAI web crawler for model training data',
    },
    {
        'pattern': re.compile(r'ChatGPT-User/', re.IGNORECASE),
        'name': 'ChatGPT-User',
        'provider': 'OpenAI',
        'category': 'retrieval',
        'description': 'ChatGPT real-time retrieval for user queries (RAG)',
    },
    {
        'pattern': re.compile(r'OAI-SearchBot/', re.IGNORECASE),
        'name': 'OAI-SearchBot',
        'provider': 'OpenAI',
        'category': 'indexing',
        'description': 'OpenAI search indexing crawler',
    },
    {
        'pattern': re.compile(r'ClaudeBot/', re.IGNORECASE),
        'name': 'ClaudeBot',
        'provider': 'Anthropic',
        'category': 'indexing',
        'description': 'Anthropic web crawler for model training',
    },
    {
        'pattern': re.compile(r'Claude-User/', re.IGNORECASE),
        'name': 'Claude-User',
        'provider': 'Anthropic',
        'category': 'retrieval',
        'description': 'Claude real-time retrieval for user queries',
    },
    {
        'pattern': re.compile(r'Google-Extended/', re.IGNORECASE),
        'name': 'Google-Extended',
        'provider': 'Google',
        'category': 'indexing',
        'description': 'Google AI training data crawler',
    },
    {
        'pattern': re.compile(r'PerplexityBot/', re.IGNORECASE),
        'name': 'PerplexityBot',
        'provider': 'Perplexity',
        'category': 'retrieval',
        'description': 'Perplexity AI search crawler',
    },
    {
        'pattern': re.compile(r'Bytespider/', re.IGNORECASE),
        'name': 'Bytespider',
        'provider': 'ByteDance',
        'category': 'indexing',
        'description': 'ByteDance/TikTok AI crawler',
    },
    {
        'pattern': re.compile(r'CCBot/', re.IGNORECASE),
        'name': 'CCBot',
        'provider': 'Common Crawl',
        'category': 'indexing',
        'description': 'Common Crawl bot',
    },
    {
        'pattern': re.compile(r'Applebot-Extended/', re.IGNORECASE),
        'name': 'Applebot-Extended',
        'provider': 'Apple',
        'category': 'indexing',
        'description': 'Apple AI/Siri training data crawler',
    },
    {
        'pattern': re.compile(r'Meta-ExternalAgent/', re.IGNORECASE),
        'name': 'Meta-ExternalAgent',
        'provider': 'Meta',
        'category': 'indexing',
        'description': 'Meta/Facebook AI training data crawler',
    },
    {
        'pattern': re.compile(r'cohere-ai/', re.IGNORECASE),
        'name': 'cohere-ai',
        'provider': 'Cohere',
        'category': 'indexing',
        'description': 'Cohere AI training data crawler',
    },
]


def classify_user_agent(user_agent: Optional[str]) -> Dict[str, Any]:
    """
    Classify a user-agent string against the AI bot database.

    Args:
        user_agent: The user-agent string to classify

    Returns:
        Dict with '$is_ai_bot' (always present) and optional
        '$ai_bot_name', '$ai_bot_provider', '$ai_bot_category'
    """
    if not user_agent or not isinstance(user_agent, str):
        return {'$is_ai_bot': False}

    for bot in AI_BOT_DATABASE:
        if bot['pattern'].search(user_agent):
            return {
                '$is_ai_bot': True,
                '$ai_bot_name': bot['name'],
                '$ai_bot_provider': bot['provider'],
                '$ai_bot_category': bot['category'],
            }

    return {'$is_ai_bot': False}


def create_classifier(
    additional_bots: Optional[List[Dict[str, Any]]] = None,
) -> Callable:
    """
    Create a classifier with optional additional bot patterns.

    Args:
        additional_bots: Additional bot patterns (checked before built-ins).
            Each entry must have 'pattern' (compiled regex), 'name', 'provider', 'category'.

    Returns:
        A classify_user_agent function.
    """
    combined = list(additional_bots or []) + AI_BOT_DATABASE

    def classifier(user_agent: Optional[str]) -> Dict[str, Any]:
        if not user_agent or not isinstance(user_agent, str):
            return {'$is_ai_bot': False}
        for bot in combined:
            if bot['pattern'].search(user_agent):
                return {
                    '$is_ai_bot': True,
                    '$ai_bot_name': bot['name'],
                    '$ai_bot_provider': bot['provider'],
                    '$ai_bot_category': bot['category'],
                }
        return {'$is_ai_bot': False}

    return classifier


def get_bot_database() -> List[Dict[str, str]]:
    """Return a copy of the bot database for inspection."""
    return [
        {
            'name': bot['name'],
            'provider': bot['provider'],
            'category': bot['category'],
            'description': bot.get('description', ''),
        }
        for bot in AI_BOT_DATABASE
    ]
