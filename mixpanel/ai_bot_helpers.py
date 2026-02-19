# mixpanel/ai_bot_helpers.py
"""Framework integration helpers for AI bot classification."""

from typing import Any, Dict, Optional


def extract_request_context_django(request: Any) -> Dict[str, str]:
    """
    Extract user-agent and IP from a Django HttpRequest.

    Usage:
        from mixpanel.ai_bot_helpers import extract_request_context_django

        mp.track('user_id', 'page_view', {
            **extract_request_context_django(request),
            'page_url': request.path,
        })
    """
    ctx = {}
    ua = request.META.get('HTTP_USER_AGENT')
    if ua:
        ctx['$user_agent'] = ua

    # Django's get_host() + REMOTE_ADDR
    ip = (
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
        or request.META.get('REMOTE_ADDR')
    )
    if ip:
        ctx['$ip'] = ip

    return ctx


def extract_request_context_flask(request: Any) -> Dict[str, str]:
    """
    Extract user-agent and IP from a Flask request.

    Usage:
        from mixpanel.ai_bot_helpers import extract_request_context_flask

        mp.track('user_id', 'page_view', {
            **extract_request_context_flask(request),
            'page_url': request.path,
        })
    """
    ctx = {}
    ua = request.headers.get('User-Agent')
    if ua:
        ctx['$user_agent'] = ua

    ip = request.remote_addr
    if ip:
        ctx['$ip'] = ip

    return ctx


def extract_request_context_fastapi(request: Any) -> Dict[str, str]:
    """
    Extract user-agent and IP from a FastAPI/Starlette Request.

    Usage:
        from mixpanel.ai_bot_helpers import extract_request_context_fastapi

        mp.track('user_id', 'page_view', {
            **extract_request_context_fastapi(request),
            'page_url': str(request.url),
        })
    """
    ctx = {}
    ua = request.headers.get('user-agent')
    if ua:
        ctx['$user_agent'] = ua

    if request.client:
        ctx['$ip'] = request.client.host

    return ctx
