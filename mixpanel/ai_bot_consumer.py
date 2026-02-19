# mixpanel/ai_bot_consumer.py
"""BotClassifyingConsumer wrapper for Mixpanel Python SDK."""

import json
from typing import Any, Dict, List, Optional

from .ai_bot_classifier import classify_user_agent, create_classifier


def _json_dumps(data):
    """Serialize data matching the SDK's json_dumps format."""
    return json.dumps(data, separators=(',', ':'))


class BotClassifyingConsumer:
    """
    Consumer wrapper that classifies AI bots in tracked events.

    Wraps any Mixpanel consumer (Consumer, BufferedConsumer, or custom)
    and enriches event data with bot classification properties when
    a user-agent string is present in the event properties.

    Usage:
        from mixpanel import Mixpanel, Consumer
        from mixpanel.ai_bot_consumer import BotClassifyingConsumer

        consumer = BotClassifyingConsumer(Consumer())
        mp = Mixpanel('YOUR_TOKEN', consumer=consumer)

        mp.track('user_id', 'page_view', {
            '$user_agent': request.headers.get('User-Agent'),
        })
    """

    def __init__(
        self,
        base_consumer: Any,
        user_agent_property: str = '$user_agent',
        additional_bots: Optional[List[Dict[str, Any]]] = None,
    ):
        """
        Args:
            base_consumer: The consumer to wrap (must have a send() method)
            user_agent_property: Property name containing the user-agent string
            additional_bots: Additional bot patterns (checked before built-ins)
        """
        self._base = base_consumer
        self._ua_prop = user_agent_property
        self._classify = (
            create_classifier(additional_bots=additional_bots)
            if additional_bots
            else classify_user_agent
        )

    def send(
        self,
        endpoint: str,
        json_message: str,
        api_key: Any = None,
        api_secret: Any = None,
    ) -> None:
        """
        Intercept event messages, classify bot user-agents, and forward.

        Only modifies 'events' endpoint messages. People, groups, and
        imports pass through unmodified.
        """
        if endpoint == 'events':
            data = json.loads(json_message)
            properties = data.get('properties', {})
            user_agent = properties.get(self._ua_prop)

            if user_agent:
                classification = self._classify(user_agent)
                properties.update(classification)
                data['properties'] = properties
                json_message = _json_dumps(data)

        self._base.send(endpoint, json_message, api_key, api_secret)

    def flush(self) -> None:
        """Proxy flush to the wrapped consumer if available."""
        if hasattr(self._base, 'flush'):
            self._base.flush()
