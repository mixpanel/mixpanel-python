"""The identity an event or profile update belongs to."""

from dataclasses import dataclass, fields
from typing import Optional, Union

# Field name -> property key it is sent as
_IDENTITY_KEYS = (
    ("distinct_id", "distinct_id"),
    ("user_id", "$user_id"),
    ("company_id", "$company_id"),
    ("device_id", "$device_id"),
)

# Field name -> key a flag evaluation context reads it from
_FLAG_CONTEXT_KEYS = (
    ("distinct_id", "distinct_id"),
    ("user_id", "$user_id"),
    ("company_id", "$company_id"),
    ("device_id", "device_id"),
)

_COMBINED_COMPANY_PREFIX = "$company:"
_COMBINED_USER_SEPARATOR = "|$user:"


def _is_id(value) -> bool:
    """True if ``value`` is an id type: a string or an integer, not a bool."""
    return isinstance(value, (str, int)) and not isinstance(value, bool)


def _parse_combined_distinct_id(distinct_id) -> Optional[tuple]:
    """Split a ``$company:{company}|$user:{user}`` distinct id.

    The company is the text up to the first ``|$user:`` and the user is
    everything after it. Returns ``(company_id, user_id)``, or None if
    ``distinct_id`` does not have that form or either part is empty.
    """
    if not isinstance(distinct_id, str) or not distinct_id.startswith(
        _COMBINED_COMPANY_PREFIX
    ):
        return None
    company_id, separator, user_id = distinct_id[
        len(_COMBINED_COMPANY_PREFIX) :
    ].partition(_COMBINED_USER_SEPARATOR)
    if not separator or not company_id or not user_id:
        return None
    return company_id, user_id


@dataclass(frozen=True, init=False)
class MixpanelIdentity:
    """Identifies who an event or profile update belongs to.

    Mixpanel resolves an identity from whichever of ``distinct_id``,
    ``$user_id``, ``$company_id`` and ``$device_id`` an event carries, so this
    type sets any combination of them and leaves the rest unset (``None``)::

        MixpanelIdentity(distinct_id="user_123")                 # a plain distinct id
        MixpanelIdentity(user_id="user_123", device_id="dev")    # simplified id merge
        MixpanelIdentity(user_id="user_123", company_id="acme")  # hierarchical groups
        MixpanelIdentity(device_id="dev")                        # anonymous, no user yet
        MixpanelIdentity(company_id="acme")                      # a company, no user

    Which combinations are valid depends on the project, so
    :class:`~mixpanel.Mixpanel` rather than this type decides. On a
    hierarchical groups project the company is part of the user's identity: a
    ``$user_id`` sent without a ``$company_id`` resolves to a different user
    that nothing reconciles later, so include the company whenever the user has
    one. Events still send a user id without one as given; user profile updates
    need the company. A user who belongs to two companies is two users, by
    design.

    On a hierarchical groups project, set ``distinct_id`` only when it is one
    Mixpanel itself built, of the form ``$company:{company}|$user:{user}``. Any
    other distinct id names a separate, unrelated user that cannot be merged
    afterwards, and a user profile update rejects it.

    Instances are immutable.

    Each id is a string or an integer and is sent as given.

    :param distinct_id: a distinct id Mixpanel resolves directly
    :type distinct_id: str or int
    :param user_id: the user's id; on a hierarchical groups project it only
        needs to be unique within the company
    :type user_id: str or int
    :param company_id: the id of the top-level company, on a hierarchical
        groups project
    :type company_id: str or int
    :param device_id: the client's device id
    :type device_id: str or int
    :raises ValueError: if a value is an empty string or not a string or an
        integer, or no value is set
    """

    distinct_id: Optional[Union[str, int]]
    user_id: Optional[Union[str, int]]
    company_id: Optional[Union[str, int]]
    device_id: Optional[Union[str, int]]

    def __init__(
        self,
        *,
        distinct_id: Optional[Union[str, int]] = None,
        user_id: Optional[Union[str, int]] = None,
        company_id: Optional[Union[str, int]] = None,
        device_id: Optional[Union[str, int]] = None,
    ):
        values = {
            "distinct_id": distinct_id,
            "user_id": user_id,
            "company_id": company_id,
            "device_id": device_id,
        }
        for name, value in values.items():
            # None leaves the value unset; an empty string is a caller error.
            if value is not None and not _is_id(value):
                msg = f"{name} must be a string or an integer, not {value!r}"
                raise ValueError(msg)
            if value == "":
                msg = f"{name} must be non-empty"
                raise ValueError(msg)
            object.__setattr__(self, name, value)
        if all(value is None for value in values.values()):
            msg = (
                "An identity needs at least one of distinct_id, user_id, "
                "company_id or device_id"
            )
            raise ValueError(msg)

    @property
    def is_hierarchical(self) -> bool:
        """True if this identity names a company, for hierarchical groups."""
        return self.company_id is not None

    def to_flag_context(
        self,
        groups: Optional[dict] = None,
        custom_properties: Optional[dict] = None,
    ) -> dict:
        """Build a feature flag evaluation context for this identity.

        Puts the ids under the keys flags read, so callers do not hand-write
        reserved keys such as ``$company_id``::

            identity.to_flag_context(
                groups={"department": "finance"},
                custom_properties={"plan": "enterprise"},
            )
            # {"$user_id": "user_123", "$company_id": "acme",
            #  "department": "finance", "custom_properties": {"plan": "enterprise"}}

        :param dict groups: group keys and values the evaluation is for, such
            as ``{"department": "finance"}``
        :param dict custom_properties: properties used by runtime targeting rules
        """
        context = dict(groups or {})
        for name, key in _FLAG_CONTEXT_KEYS:
            value = getattr(self, name)
            if value is not None:
                context[key] = value
        if custom_properties:
            context["custom_properties"] = dict(custom_properties)
        return context

    def _apply_to(self, properties: dict) -> None:
        """Write this identity's keys into ``properties``, replacing any there."""
        for name, key in _IDENTITY_KEYS:
            value = getattr(self, name)
            if value is not None:
                properties[key] = value

    def __repr__(self):
        set_fields = ", ".join(
            f"{f.name}={getattr(self, f.name)!r}"
            for f in fields(self)
            if getattr(self, f.name) is not None
        )
        return f"MixpanelIdentity({set_fields})"
