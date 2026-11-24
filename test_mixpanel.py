from __future__ import annotations

import base64
import datetime
import decimal
import json
import re
import time
from unittest.mock import AsyncMock, MagicMock, patch
from urllib import parse as urllib_parse

import pytest
import responses
from responses.matchers import urlencoded_params_matcher

import mixpanel
from mixpanel import MixpanelIdentity
from mixpanel.flags.utils import exposure_identity


class LogConsumer:
    def __init__(self):
        self.log = []

    def send(self, endpoint, event, api_key=None):
        entry = [endpoint, json.loads(event)]
        # Only append api_key if it's not (None, None)
        if api_key is not None:
            # api_key might be a single value or (api_key, api_secret) tuple
            if isinstance(api_key, tuple):
                # Don't append if it's (None, None)
                if api_key != (None, None):
                    entry.append(api_key)
            else:
                entry.append(api_key)
        self.log.append(tuple(entry))

    def clear(self):
        self.log = []


class TestMixpanelBase:
    TOKEN = "12345"

    def setup_method(self):
        self.consumer = LogConsumer()
        self.mp = mixpanel.Mixpanel(self.TOKEN, consumer=self.consumer)
        self.mp._now = lambda: 1000.1
        self.mp._make_insert_id = lambda: "abcdefg"


class TestMixpanelTracking(TestMixpanelBase):
    def test_track(self):
        self.mp.track(
            "ID",
            "button press",
            {"size": "big", "color": "blue", "$insert_id": "abc123"},
        )
        assert self.consumer.log == [
            (
                "events",
                {
                    "event": "button press",
                    "properties": {
                        "token": self.TOKEN,
                        "size": "big",
                        "color": "blue",
                        "distinct_id": "ID",
                        "time": self.mp._now(),
                        "$insert_id": "abc123",
                        "mp_lib": "python",
                        "$lib_version": mixpanel.__version__,
                    },
                },
            )
        ]

    def test_track_makes_insert_id(self):
        self.mp.track("ID", "button press", {"size": "big"})
        props = self.consumer.log[0][1]["properties"]
        assert "$insert_id" in props
        assert isinstance(props["$insert_id"], str)
        assert len(props["$insert_id"]) > 0

    def test_track_empty(self):
        self.mp.track("person_xyz", "login", {})
        assert self.consumer.log == [
            (
                "events",
                {
                    "event": "login",
                    "properties": {
                        "token": self.TOKEN,
                        "distinct_id": "person_xyz",
                        "time": self.mp._now(),
                        "$insert_id": self.mp._make_insert_id(),
                        "mp_lib": "python",
                        "$lib_version": mixpanel.__version__,
                    },
                },
            )
        ]

    def test_import_data(self):
        timestamp = time.time()
        self.mp.import_data(
            "MY_API_KEY",
            "ID",
            "button press",
            timestamp,
            {"size": "big", "color": "blue", "$insert_id": "abc123"},
            api_secret="MY_SECRET",
        )
        assert self.consumer.log == [
            (
                "imports",
                {
                    "event": "button press",
                    "properties": {
                        "token": self.TOKEN,
                        "size": "big",
                        "color": "blue",
                        "distinct_id": "ID",
                        "time": timestamp,
                        "$insert_id": "abc123",
                        "mp_lib": "python",
                        "$lib_version": mixpanel.__version__,
                    },
                },
                ("MY_API_KEY", "MY_SECRET"),
            )
        ]

    def test_track_meta(self):
        self.mp.track(
            "ID",
            "button press",
            {"size": "big", "color": "blue", "$insert_id": "abc123"},
            meta={"ip": 0},
        )
        assert self.consumer.log == [
            (
                "events",
                {
                    "event": "button press",
                    "properties": {
                        "token": self.TOKEN,
                        "size": "big",
                        "color": "blue",
                        "distinct_id": "ID",
                        "time": self.mp._now(),
                        "$insert_id": "abc123",
                        "mp_lib": "python",
                        "$lib_version": mixpanel.__version__,
                    },
                    "ip": 0,
                },
            )
        ]


class TestMixpanelPeople(TestMixpanelBase):
    def test_people_set(self):
        self.mp.people_set(
            "amq", {"birth month": "october", "favorite color": "purple"}
        )
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$set": {
                        "birth month": "october",
                        "favorite color": "purple",
                    },
                },
            )
        ]

    def test_people_set_once(self):
        self.mp.people_set_once(
            "amq", {"birth month": "october", "favorite color": "purple"}
        )
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$set_once": {
                        "birth month": "october",
                        "favorite color": "purple",
                    },
                },
            )
        ]

    def test_people_increment(self):
        self.mp.people_increment("amq", {"Albums Released": 1})
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$add": {
                        "Albums Released": 1,
                    },
                },
            )
        ]

    def test_people_append(self):
        self.mp.people_append(
            "amq", {"birth month": "october", "favorite color": "purple"}
        )
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$append": {
                        "birth month": "october",
                        "favorite color": "purple",
                    },
                },
            )
        ]

    def test_people_union(self):
        self.mp.people_union("amq", {"Albums": ["Diamond Dogs"]})
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$union": {
                        "Albums": ["Diamond Dogs"],
                    },
                },
            )
        ]

    def test_people_unset(self):
        self.mp.people_unset("amq", ["Albums", "Singles"])
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$unset": ["Albums", "Singles"],
                },
            )
        ]

    def test_people_remove(self):
        self.mp.people_remove("amq", {"Albums": "Diamond Dogs"})
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$remove": {"Albums": "Diamond Dogs"},
                },
            )
        ]

    def test_people_track_charge(self):
        self.mp.people_track_charge("amq", 12.65, {"$time": "2013-04-01T09:02:00"})
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$append": {
                        "$transactions": {
                            "$time": "2013-04-01T09:02:00",
                            "$amount": 12.65,
                        },
                    },
                },
            )
        ]

    def test_people_track_charge_without_properties(self):
        self.mp.people_track_charge("amq", 12.65)
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$append": {
                        "$transactions": {
                            "$amount": 12.65,
                        },
                    },
                },
            )
        ]

    def test_people_clear_charges(self):
        self.mp.people_clear_charges("amq")
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$unset": ["$transactions"],
                },
            )
        ]

    def test_people_set_created_date_string(self):
        created = "2014-02-14T01:02:03"
        self.mp.people_set("amq", {"$created": created, "favorite color": "purple"})
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$set": {
                        "$created": created,
                        "favorite color": "purple",
                    },
                },
            )
        ]

    def test_people_set_created_date_datetime(self):
        created = datetime.datetime(2014, 2, 14, 1, 2, 3)  # noqa: DTZ001
        self.mp.people_set("amq", {"$created": created, "favorite color": "purple"})
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$set": {
                        "$created": "2014-02-14T01:02:03",
                        "favorite color": "purple",
                    },
                },
            )
        ]

    def test_people_meta(self):
        self.mp.people_set(
            "amq",
            {"birth month": "october", "favorite color": "purple"},
            meta={"$ip": 0, "$ignore_time": True},
        )
        assert self.consumer.log == [
            (
                "people",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$distinct_id": "amq",
                    "$set": {
                        "birth month": "october",
                        "favorite color": "purple",
                    },
                    "$ip": 0,
                    "$ignore_time": True,
                },
            )
        ]


class TestMixpanelIdentity(TestMixpanelBase):
    def test_alias(self):
        # More complicated since alias() forces a synchronous call.

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/track",
                json={"status": 1, "error": None},
                status=200,
            )

            self.mp.alias("ALIAS", "ORIGINAL ID")

            assert self.consumer.log == []
            call = rsps.calls[0]
            assert call.request.method == "POST"
            assert call.request.url == "https://api.mixpanel.com/track"
            body = (
                call.request.body
                if isinstance(call.request.body, str)
                else call.request.body.decode("utf-8")
            )
            posted_data = dict(urllib_parse.parse_qsl(body))
            assert json.loads(posted_data["data"]) == {
                "event": "$create_alias",
                "properties": {
                    "alias": "ALIAS",
                    "token": "12345",
                    "distinct_id": "ORIGINAL ID",
                },
            }

    def test_alias_with_service_account(self):
        """Test that alias() does NOT use service account credentials.

        Service account credentials are only for /import and feature flag endpoints.
        alias() uses the /track endpoint and should not include auth headers.
        """
        credentials = mixpanel.ServiceAccountCredentials(
            username="test_user", secret="test_secret", project_id="test_project_id"
        )
        mp = mixpanel.Mixpanel("12345", credentials=credentials)

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/track",
                json={"status": 1, "error": None},
                status=200,
            )

            mp.alias("ALIAS", "ORIGINAL ID")

            call = rsps.calls[0]
            assert call.request.method == "POST"
            # Should NOT have project_id query parameter - credentials not used for /track
            assert "project_id" not in call.request.url
            # Should NOT have basic auth header - credentials not used for /track
            auth_header = call.request.headers.get("Authorization")
            assert auth_header is None
            # Verify the payload
            body = (
                call.request.body
                if isinstance(call.request.body, str)
                else call.request.body.decode("utf-8")
            )
            posted_data = dict(urllib_parse.parse_qsl(body))
            assert json.loads(posted_data["data"]) == {
                "event": "$create_alias",
                "properties": {
                    "alias": "ALIAS",
                    "token": "12345",
                    "distinct_id": "ORIGINAL ID",
                },
            }

    def test_merge(self):
        self.mp.merge("my_good_api_key", "d1", "d2")
        assert self.consumer.log == [
            (
                "imports",
                {
                    "event": "$merge",
                    "properties": {
                        "$distinct_ids": ["d1", "d2"],
                        "token": self.TOKEN,
                    },
                },
                ("my_good_api_key", None),
            )
        ]

        self.consumer.clear()

        self.mp.merge("my_good_api_key", "d1", "d2", api_secret="my_secret")
        assert self.consumer.log == [
            (
                "imports",
                {
                    "event": "$merge",
                    "properties": {
                        "$distinct_ids": ["d1", "d2"],
                        "token": self.TOKEN,
                    },
                },
                ("my_good_api_key", "my_secret"),
            )
        ]


class TestMixpanelGroups(TestMixpanelBase):
    def test_group_set(self):
        self.mp.group_set(
            "company", "amq", {"birth month": "october", "favorite color": "purple"}
        )
        assert self.consumer.log == [
            (
                "groups",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$group_key": "company",
                    "$group_id": "amq",
                    "$set": {
                        "birth month": "october",
                        "favorite color": "purple",
                    },
                },
            )
        ]

    def test_group_set_once(self):
        self.mp.group_set_once(
            "company", "amq", {"birth month": "october", "favorite color": "purple"}
        )
        assert self.consumer.log == [
            (
                "groups",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$group_key": "company",
                    "$group_id": "amq",
                    "$set_once": {
                        "birth month": "october",
                        "favorite color": "purple",
                    },
                },
            )
        ]

    def test_group_union(self):
        self.mp.group_union("company", "amq", {"Albums": ["Diamond Dogs"]})
        assert self.consumer.log == [
            (
                "groups",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$group_key": "company",
                    "$group_id": "amq",
                    "$union": {
                        "Albums": ["Diamond Dogs"],
                    },
                },
            )
        ]

    def test_group_unset(self):
        self.mp.group_unset("company", "amq", ["Albums", "Singles"])
        assert self.consumer.log == [
            (
                "groups",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$group_key": "company",
                    "$group_id": "amq",
                    "$unset": ["Albums", "Singles"],
                },
            )
        ]

    def test_group_remove(self):
        self.mp.group_remove("company", "amq", {"Albums": "Diamond Dogs"})
        assert self.consumer.log == [
            (
                "groups",
                {
                    "$time": self.mp._now(),
                    "$token": self.TOKEN,
                    "$group_key": "company",
                    "$group_id": "amq",
                    "$remove": {"Albums": "Diamond Dogs"},
                },
            )
        ]

    def test_custom_json_serializer(self):
        decimal_string = "12.05"
        with pytest.raises(TypeError) as excinfo:
            self.mp.track(
                "ID", "button press", {"size": decimal.Decimal(decimal_string)}
            )
        assert "not JSON serializable" in str(excinfo.value)

        class CustomSerializer(mixpanel.DatetimeSerializer):
            def default(self, obj):
                if isinstance(obj, decimal.Decimal):
                    return obj.to_eng_string()
                return super().default(obj)

        self.mp._serializer = CustomSerializer
        self.mp.track(
            "ID",
            "button press",
            {"size": decimal.Decimal(decimal_string), "$insert_id": "abc123"},
        )
        assert self.consumer.log == [
            (
                "events",
                {
                    "event": "button press",
                    "properties": {
                        "token": self.TOKEN,
                        "size": decimal_string,
                        "distinct_id": "ID",
                        "time": self.mp._now(),
                        "$insert_id": "abc123",
                        "mp_lib": "python",
                        "$lib_version": mixpanel.__version__,
                    },
                },
            )
        ]


class RawConsumer:
    def __init__(self):
        self.log = []

    def send(self, endpoint, message, api_key=None):
        self.log.append((endpoint, message, api_key))


class TestHierarchicalGroups:
    TOKEN = "test-token"
    COMBINED_ID = "$company:acme|$user:user_123"

    def setup_method(self):
        self.consumer = LogConsumer()
        self.hg = mixpanel.Mixpanel(
            self.TOKEN, consumer=self.consumer, hierarchical_groups=True
        )
        self.legacy = mixpanel.Mixpanel(self.TOKEN, consumer=self.consumer)
        for mp in (self.hg, self.legacy):
            mp._now = lambda: 1000.1
            mp._make_insert_id = lambda: "abcdefg"

    def last(self):
        return self.consumer.log[-1]

    def last_message(self):
        return self.consumer.log[-1][1]

    def last_properties(self):
        return self.consumer.log[-1][1]["properties"]

    # Identity

    def test_identity_rejects_empty_values(self):
        # An empty string is a caller error; None simply leaves the value unset.
        for name in ("distinct_id", "user_id", "company_id", "device_id"):
            with pytest.raises(ValueError, match=name):
                mixpanel.MixpanelIdentity(**{name: ""})

    def test_identity_accepts_string_and_integer_ids(self):
        identity = mixpanel.MixpanelIdentity(
            distinct_id=0, user_id=42, company_id=7, device_id="dev"
        )

        assert identity.distinct_id == 0
        assert identity.user_id == 42
        assert identity.company_id == 7
        assert identity.device_id == "dev"

        # Ingestion drops integer ids, so every identity id is sent as a string.
        self.hg.track(identity, "event")
        properties = self.last_properties()
        assert properties["distinct_id"] == "0"
        assert properties["$user_id"] == "42"
        assert properties["$company_id"] == "7"
        assert properties["$device_id"] == "dev"

    def test_identity_rejects_other_id_types(self):
        for name in ("distinct_id", "user_id", "company_id", "device_id"):
            for value in (True, False, 1.5, ["a"], {"a": 1}, b"a"):
                with pytest.raises(ValueError, match=name):
                    mixpanel.MixpanelIdentity(**{name: value})

    def test_identity_needs_at_least_one_value(self):
        with pytest.raises(ValueError, match="at least one"):
            mixpanel.MixpanelIdentity()
        with pytest.raises(ValueError, match="at least one"):
            mixpanel.MixpanelIdentity(user_id=None, company_id=None)

    def test_none_leaves_a_value_unset(self):
        identity = mixpanel.MixpanelIdentity(user_id="user_123", device_id=None)

        assert identity.user_id == "user_123"
        assert identity.device_id is None
        assert not identity.is_hierarchical

    def test_identity_is_immutable_keyword_only_and_readable(self):
        identity = mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme")

        assert identity.is_hierarchical
        with pytest.raises(AttributeError):
            identity.user_id = "other"
        with pytest.raises(TypeError):
            mixpanel.MixpanelIdentity("user_123")
        assert (
            repr(identity) == "MixpanelIdentity(user_id='user_123', company_id='acme')"
        )
        assert identity == mixpanel.MixpanelIdentity(
            company_id="acme", user_id="user_123"
        )

    def test_identity_builds_a_flag_context(self):
        identity = mixpanel.MixpanelIdentity(
            user_id="user_123", company_id="acme", device_id="device_abc"
        )

        assert identity.to_flag_context(
            groups={"department": "finance"},
            custom_properties={"plan": "enterprise"},
        ) == {
            "$user_id": "user_123",
            "$company_id": "acme",
            "device_id": "device_abc",
            "department": "finance",
            "custom_properties": {"plan": "enterprise"},
        }

    def test_identity_builds_a_flag_context_from_a_plain_distinct_id(self):
        identity = mixpanel.MixpanelIdentity(distinct_id="user_123")

        assert identity.to_flag_context() == {"distinct_id": "user_123"}

    def test_identity_flag_context_ids_are_strings(self):
        # Flags read ids only as strings; group values and custom properties
        # are passed through as given.
        identity = mixpanel.MixpanelIdentity(
            distinct_id=1, user_id=42, company_id=7, device_id=5
        )

        assert identity.to_flag_context(
            groups={"team_id": 9}, custom_properties={"seats": 3}
        ) == {
            "distinct_id": "1",
            "$user_id": "42",
            "$company_id": "7",
            "device_id": "5",
            "team_id": 9,
            "custom_properties": {"seats": 3},
        }

    def test_identity_ids_are_strings_without_hierarchical_groups(self):
        self.legacy.track(
            mixpanel.MixpanelIdentity(distinct_id=1, user_id=42, device_id=5),
            "event",
            {"$user_id": 3, "count": 4},
        )

        properties = self.last_properties()
        assert properties["distinct_id"] == "1"
        assert properties["$user_id"] == "42"
        assert properties["$device_id"] == "5"
        assert properties["count"] == 4

    # Events

    def test_hierarchical_event_sends_user_and_company_without_distinct_id(self):
        self.hg.track(
            mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme"), "Signup"
        )

        props = self.last_properties()
        assert props["$user_id"] == "user_123"
        assert props["$company_id"] == "acme"
        assert "distinct_id" not in props
        assert "$device_id" not in props
        assert props["token"] == self.TOKEN

    def test_hierarchical_event_with_device_id(self):
        self.hg.track(
            mixpanel.MixpanelIdentity(
                user_id="user_123", company_id="acme", device_id="device_abc"
            ),
            "Signup",
        )

        props = self.last_properties()
        assert props["$device_id"] == "device_abc"
        assert "distinct_id" not in props

    def test_company_only_event(self):
        self.hg.track(mixpanel.MixpanelIdentity(company_id="acme"), "Renewed")

        props = self.last_properties()
        assert props["$company_id"] == "acme"
        assert "$user_id" not in props
        assert "distinct_id" not in props

    def test_legacy_identity_sends_distinct_id(self):
        self.legacy.track(mixpanel.MixpanelIdentity(distinct_id="user_123"), "Signup")

        props = self.last_properties()
        assert props["distinct_id"] == "user_123"
        assert "$user_id" not in props
        assert "$company_id" not in props

    def test_legacy_identity_event_matches_plain_distinct_id(self):
        self.legacy.track("user_123", "Signup", {"plan": "pro"})
        self.legacy.track(
            mixpanel.MixpanelIdentity(distinct_id="user_123"), "Signup", {"plan": "pro"}
        )

        assert self.consumer.log[0] == self.consumer.log[1]

    def test_identity_without_distinct_id_keeps_caller_distinct_id(self):
        self.hg.track(
            mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme"),
            "Signup",
            {"distinct_id": "caller"},
        )
        assert self.last_properties()["distinct_id"] == "caller"

        self.hg.track(
            mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme"),
            "Signup",
        )
        assert "distinct_id" not in self.last_properties()

    def test_identity_overrides_caller_supplied_keys_and_keeps_other_properties(self):
        caller = {"$company_id": "wrong", "plan": "enterprise"}

        self.hg.track(
            mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme"),
            "Signup",
            caller,
        )

        props = self.last_properties()
        assert props["$company_id"] == "acme"
        assert props["plan"] == "enterprise"
        assert caller["$company_id"] == "wrong"

    def test_hierarchical_import_event(self):
        self.hg.import_data(
            None,
            mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme"),
            "Signup",
            1000,
        )

        endpoint, message = self.last()
        assert endpoint == "imports"
        props = message["properties"]
        assert props["$user_id"] == "user_123"
        assert props["$company_id"] == "acme"
        assert props["time"] == 1000
        assert "distinct_id" not in props
        assert "$insert_id" in props

    def test_user_and_device_without_company_is_valid_for_simplified_id_merge(self):
        # $user_id with $device_id is the standard non-hierarchical server-side identity.
        self.legacy.track(
            mixpanel.MixpanelIdentity(user_id="user_123", device_id="device_abc"),
            "Signup",
        )

        props = self.last_properties()
        assert props["$user_id"] == "user_123"
        assert props["$device_id"] == "device_abc"
        assert "distinct_id" not in props
        assert "$company_id" not in props

    def test_user_without_company_is_sent_as_given_for_hierarchical_groups(self):
        self.hg.track(mixpanel.MixpanelIdentity(user_id="user_123"), "Signup")

        props = self.last_properties()
        assert props["$user_id"] == "user_123"
        assert "$company_id" not in props

    def test_user_with_device_but_no_company_is_allowed_for_hierarchical_groups(self):
        # Mixpanel ignores the user id and keeps the event under the device, which
        # later links to the company-scoped user. Recoverable, so not refused.
        self.hg.track(
            mixpanel.MixpanelIdentity(user_id="user_123", device_id="device_abc"),
            "Signup",
        )

        props = self.last_properties()
        assert props["$device_id"] == "device_abc"
        assert "$company_id" not in props

    def test_anonymous_device_event(self):
        for mp in (self.hg, self.legacy):
            mp.track(mixpanel.MixpanelIdentity(device_id="device_abc"), "Page View")

            props = self.last_properties()
            assert props["$device_id"] == "device_abc"
            assert "distinct_id" not in props
            assert "$user_id" not in props
            assert "$company_id" not in props

    def test_combined_distinct_id_event_passes_through(self):
        # Ingestion parses $company:{company}|$user:{user} back into $company_id and
        # $user_id, so it resolves to the same user as the identity form.
        self.hg.track(self.COMBINED_ID, "Signup")
        self.hg.track(mixpanel.MixpanelIdentity(distinct_id=self.COMBINED_ID), "Signup")

        for _, message in self.consumer.log:
            assert message["properties"]["distinct_id"] == self.COMBINED_ID
            assert "$user_id" not in message["properties"]

    def test_raw_distinct_id_events_are_not_refused(self):
        self.hg.track("user_123", "Signup")
        assert self.last_properties()["distinct_id"] == "user_123"
        self.hg.import_data(None, "user_123", "Signup", 1000)
        assert self.last_properties()["distinct_id"] == "user_123"
        self.legacy.track("user_123", "Signup")
        assert self.last_properties()["distinct_id"] == "user_123"

    def test_hierarchical_identity_requires_hierarchical_client(self):
        identity = mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme")

        with pytest.raises(ValueError, match="hierarchical_groups=True"):
            self.legacy.people_set(identity, {"role": "admin"})
        with pytest.raises(ValueError, match="hierarchical_groups=True"):
            self.legacy.track(identity, "Signup")
        with pytest.raises(ValueError, match="hierarchical_groups=True"):
            self.legacy.import_data(None, identity, "Signup", 1000)
        with pytest.raises(ValueError, match="hierarchical_groups=True"):
            self.legacy.track(mixpanel.MixpanelIdentity(company_id="acme"), "Renewed")
        assert self.consumer.log == []

    def test_none_identity_is_not_an_identity(self):
        # None is a plain (if unhelpful) distinct id, as before.
        self.hg.track(None, "Signup")
        assert self.last_properties()["distinct_id"] is None

    # User profiles

    def test_add_and_append_raise_for_hierarchical_groups(self):
        # A hierarchical groups user profile is a group profile, and /groups has no
        # $add or $append, so these have no valid path at all.
        error = mixpanel.UnsupportedOperationError
        with pytest.raises(error):
            self.hg.people_increment("user_123", {"logins": 1})
        with pytest.raises(error):
            self.hg.people_append("user_123", {"plan": "pro"})
        with pytest.raises(error):
            self.hg.people_track_charge("user_123", 9.99)
        with pytest.raises(error):
            self.hg.people_update({"$distinct_id": "user_123", "$add": {"n": 1}})
        with pytest.raises(error):
            self.hg.people_update({"$distinct_id": "user_123", "$append": {"n": 1}})
        with pytest.raises(error):
            self.hg.people_update({"$distinct_id": "user_123", "$merge": {}})
        assert self.consumer.log == []

    def test_alias_raises_on_hierarchical_groups(self):
        with responses.RequestsMock() as rsps:
            with pytest.raises(mixpanel.UnsupportedOperationError):
                self.hg.alias("$company:acme|$user:u2", self.COMBINED_ID)
            assert len(rsps.calls) == 0

    def test_merge_raises_on_hierarchical_groups(self):
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.hg.merge(None, self.COMBINED_ID, "$company:acme|$user:u2")
        assert self.consumer.log == []

    def test_add_and_append_error_names_what_is_supported(self):
        with pytest.raises(mixpanel.UnsupportedOperationError) as excinfo:
            self.hg.people_increment("user_123", {"logins": 1})

        message = str(excinfo.value)
        assert "$add" in message
        assert "$set, $set_once, $unset, $union, $remove, $delete" in message
        assert "people_increment, people_append and people_track_charge" in message

    def test_unsupported_people_methods_refuse_an_identity(self):
        identity = mixpanel.MixpanelIdentity(distinct_id="user_123")

        with pytest.raises(ValueError, match="does not accept a MixpanelIdentity"):
            self.legacy.people_increment(identity, {"logins": 1})
        with pytest.raises(ValueError, match="does not accept a MixpanelIdentity"):
            self.legacy.people_append(identity, {"plan": "pro"})
        with pytest.raises(ValueError, match="does not accept a MixpanelIdentity"):
            self.legacy.people_track_charge(identity, 9.99)
        assert self.consumer.log == []

    def test_supported_people_methods_work_for_hierarchical_groups(self):
        # A combined distinct id is sent to /groups as its company and user.
        cid = self.COMBINED_ID
        self.hg.people_set(cid, {"plan": "pro"})
        self.hg.people_set_once(cid, {"plan": "pro"})
        self.hg.people_delete(cid)
        self.hg.people_remove(cid, {"tags": "a"})
        self.hg.people_union(cid, {"tags": ["a"]})
        self.hg.people_unset(cid, ["plan"])
        self.hg.people_update({"$distinct_id": cid, "$set": {"a": 1}}, meta={"$ip": 0})

        operations = [
            "$set",
            "$set_once",
            "$delete",
            "$remove",
            "$union",
            "$unset",
            "$set",
        ]
        assert len(self.consumer.log) == len(operations)
        for (endpoint, message), operation in zip(self.consumer.log, operations):
            assert endpoint == "groups"
            assert operation in message
            assert "$distinct_id" not in message
            assert message["$group_key"] == "$user_id"
            assert message["$group_id"] == "user_123"
            assert message["$company_id"] == "acme"
        assert self.last_message()["$ip"] == 0

    def test_combined_distinct_id_matches_identity_profile_update(self):
        hg_identity = mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme")
        meta = {"$ip": "1.2.3.4", "$ignore_time": True}
        for profile in (hg_identity, self.COMBINED_ID):
            self.hg.people_set(profile, {"plan": "pro"}, meta=meta)
            self.hg.people_unset(profile, ["plan"])
            self.hg.people_delete(profile)

        first, second = self.consumer.log[:3], self.consumer.log[3:]
        assert first == second
        assert [list(message) for _, message in first] == [
            list(message) for _, message in second
        ]
        assert first[0] == (
            "groups",
            {
                "$token": self.TOKEN,
                "$time": 1000.1,
                "$group_key": "$user_id",
                "$group_id": "user_123",
                "$set": {"plan": "pro"},
                "$ip": "1.2.3.4",
                "$ignore_time": True,
                "$company_id": "acme",
            },
        )

    def test_raw_distinct_id_profile_update_is_rejected(self):
        identity = mixpanel.MixpanelIdentity(distinct_id="user_123")
        calls = [
            lambda p: self.hg.people_set(p, {"plan": "pro"}),
            lambda p: self.hg.people_set_once(p, {"plan": "pro"}),
            lambda p: self.hg.people_unset(p, ["plan"]),
            lambda p: self.hg.people_union(p, {"tags": ["a"]}),
            lambda p: self.hg.people_remove(p, {"tags": "a"}),
            self.hg.people_delete,
        ]
        for call in calls:
            for profile in ("user_123", identity):
                with pytest.raises(ValueError, match="need a user and a company") as e:
                    call(profile)
                message = str(e.value)
                assert "MixpanelIdentity(user_id=..., company_id=...)" in message
                assert "$company:{company}|$user:{user}" in message
                assert not isinstance(e.value, mixpanel.CompanyRequiredError)
        assert self.consumer.log == []

    @pytest.mark.parametrize(
        "distinct_id",
        [
            "$company:acme",  # missing user and separator
            "$company:$user:user_123",  # missing separator
            "company:acme|$user:user_123",  # wrong prefix
            "$user:user_123|$company:acme",  # parts reversed
            " $company:acme|$user:user_123",  # leading space
            "",
        ],
    )
    def test_malformed_combined_distinct_id_is_rejected(self, distinct_id):
        with pytest.raises(ValueError, match="need a user and a company"):
            self.hg.people_set(distinct_id, {"plan": "pro"})
        with pytest.raises(ValueError, match="need a user and a company"):
            self.hg.people_update({"$distinct_id": distinct_id, "$set": {"a": 1}})
        assert self.consumer.log == []

    def test_combined_distinct_id_with_pipe_in_a_part_is_rejected(self):
        # The company is the text up to the first |$user:, so either part may
        # come out containing "|", which /groups cannot split again.
        for distinct_id, part in (
            ("$company:a|b|$user:u", "company"),
            ("$company:a|$user:u|$user:v", "user"),
            ("$company:a|$user:u|v", "user"),
        ):
            with pytest.raises(ValueError, match=f"names a {part} containing"):
                self.hg.people_set(distinct_id, {"plan": "pro"})
            with pytest.raises(ValueError, match=f"names a {part} containing"):
                self.hg.track(distinct_id, "event")
            with pytest.raises(ValueError, match=f"names a {part} containing"):
                self.hg.track(
                    mixpanel.MixpanelIdentity(distinct_id=distinct_id), "event"
                )
        assert self.consumer.log == []

    def test_combined_distinct_id_identity_with_device_goes_to_groups(self):
        identity = mixpanel.MixpanelIdentity(
            distinct_id=self.COMBINED_ID, device_id="dev"
        )

        self.hg.people_set(identity, {"plan": "pro"})

        endpoint, message = self.last()
        assert endpoint == "groups"
        assert message["$group_id"] == "user_123"
        assert message["$company_id"] == "acme"

    def test_people_update_rewrites_combined_distinct_id(self):
        self.hg.people_update(
            {
                "$distinct_id": self.COMBINED_ID,
                "$set": {"plan": "pro"},
                "$ignore_time": True,
            },
            meta={"$ip": 0},
        )

        assert self.last() == (
            "groups",
            {
                "$token": self.TOKEN,
                "$time": 1000.1,
                "$group_key": "$user_id",
                "$group_id": "user_123",
                "$set": {"plan": "pro"},
                "$ignore_time": True,
                "$ip": 0,
                "$company_id": "acme",
            },
        )

    def test_people_update_refuses_company_conflicting_with_distinct_id(self):
        with pytest.raises(ValueError, match=r"names company 'acme', but \$company_id"):
            self.hg.people_update(
                {"$distinct_id": self.COMBINED_ID, "$set": {"plan": "pro"}},
                meta={"$company_id": "other"},
            )
        assert self.consumer.log == []

    def test_people_update_refuses_profile_keys_conflicting_with_distinct_id(self):
        conflicts = (
            {"$group_id": "bob"},
            {"$group_key": "company"},
            {"$company_id": "other"},
        )
        for conflict in conflicts:
            with pytest.raises(ValueError, match=r"names .*, but \$"):
                self.hg.people_update(
                    {
                        "$distinct_id": "$company:acme|$user:alice",
                        "$delete": "",
                        **conflict,
                    }
                )
            with pytest.raises(ValueError, match=r"names .*, but \$"):
                self.hg.people_update(
                    {"$distinct_id": "$company:acme|$user:alice", "$delete": ""},
                    meta=conflict,
                )
        assert self.consumer.log == []

        self.hg.people_update(
            {
                "$distinct_id": "$company:acme|$user:alice",
                "$group_key": "$user_id",
                "$group_id": "alice",
                "$delete": "",
            },
            meta={"$company_id": "acme"},
        )
        message = self.last_message()
        assert message["$group_key"] == "$user_id"
        assert message["$group_id"] == "alice"
        assert message["$company_id"] == "acme"

    def test_people_update_uses_distinct_id_from_meta(self):
        self.hg.people_update(
            {"$distinct_id": "user_123", "$set": {"a": 1}},
            meta={"$distinct_id": self.COMBINED_ID},
        )

        endpoint, message = self.last()
        assert endpoint == "groups"
        assert "$distinct_id" not in message
        assert message["$group_id"] == "user_123"
        assert message["$company_id"] == "acme"

        with pytest.raises(ValueError, match="need a user and a company"):
            self.hg.people_update(
                {"$distinct_id": self.COMBINED_ID, "$set": {"a": 1}},
                meta={"$distinct_id": "user_123"},
            )
        assert len(self.consumer.log) == 1

    def test_people_update_without_distinct_id_is_rejected(self):
        with pytest.raises(ValueError, match="need a user and a company"):
            self.hg.people_update({"$set": {"a": 1}})
        assert self.consumer.log == []

    def test_unsupported_operations_raise_before_distinct_id_is_checked(self):
        error = mixpanel.UnsupportedOperationError
        for distinct_id in (self.COMBINED_ID, "user_123", "$company:|$user:"):
            with pytest.raises(error):
                self.hg.people_increment(distinct_id, {"logins": 1})
            with pytest.raises(error):
                self.hg.people_append(distinct_id, {"plan": "pro"})
            with pytest.raises(error):
                self.hg.people_track_charge(distinct_id, 9.99)
            with pytest.raises(error):
                self.hg.people_clear_charges(distinct_id)
            with pytest.raises(error):
                self.hg.people_update({"$distinct_id": distinct_id, "$add": {"n": 1}})
        assert self.consumer.log == []

    def test_legacy_combined_distinct_id_profile_update_goes_to_engage(self):
        self.legacy.people_set(self.COMBINED_ID, {"plan": "pro"})
        self.legacy.people_update({"$distinct_id": "user_123", "$set": {"a": 1}})

        assert [endpoint for endpoint, _ in self.consumer.log] == ["people", "people"]
        assert self.consumer.log[0][1]["$distinct_id"] == self.COMBINED_ID
        assert self.consumer.log[1][1]["$distinct_id"] == "user_123"

    def test_identity_set_reroutes_to_user_group_profile(self):
        self.hg.people_set(
            mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme"),
            {"role": "admin"},
        )

        assert self.last() == (
            "groups",
            {
                "$token": self.TOKEN,
                "$time": 1000.1,
                "$group_key": "$user_id",
                "$group_id": "user_123",
                "$set": {"role": "admin"},
                "$company_id": "acme",
            },
        )

    def test_every_identity_profile_operation_reroutes(self):
        identity = mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme")
        self.hg.people_set(identity, {"plan": "pro"})
        self.hg.people_set_once(identity, {"plan": "pro"})
        self.hg.people_delete(identity)
        self.hg.people_remove(identity, {"tags": "a"})
        self.hg.people_union(identity, {"tags": ["a"]})
        self.hg.people_unset(identity, ["plan"])

        operations = ["$set", "$set_once", "$delete", "$remove", "$union", "$unset"]
        assert len(self.consumer.log) == len(operations)
        for (endpoint, message), operation in zip(self.consumer.log, operations):
            assert endpoint == "groups"
            assert operation in message
            assert message["$company_id"] == "acme"
            assert message["$group_key"] == "$user_id"
            assert message["$group_id"] == "user_123"

    def test_identity_from_the_bound_company_is_accepted(self):
        self.hg.for_company("acme").people_set(
            mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme"),
            {"role": "admin"},
        )

        assert self.last_message()["$company_id"] == "acme"

    def test_identity_from_another_company_is_refused_on_a_bound_client(self):
        with pytest.raises(ValueError, match="bound to company 'other'"):
            self.hg.for_company("other").people_set(
                mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme"),
                {"role": "admin"},
            )
        with pytest.raises(ValueError, match="belongs to company 'acme'"):
            self.hg.for_company("other").people_set(self.COMBINED_ID, {"role": "admin"})
        assert self.consumer.log == []

    def test_identity_profile_uses_company_id_meta_when_identity_has_no_company(self):
        identity = mixpanel.MixpanelIdentity(user_id="user_123", device_id="dev")

        self.hg.people_set(identity, {"role": "admin"}, meta={"$company_id": "acme"})

        message = self.last_message()
        assert message["$company_id"] == "acme"
        assert message["$group_id"] == "user_123"

        with pytest.raises(mixpanel.CompanyRequiredError):
            self.hg.people_set(identity, {"role": "admin"})

    def test_identity_without_company_uses_the_bound_company(self):
        acme = self.hg.for_company("acme")
        identity = mixpanel.MixpanelIdentity(user_id="user_123")

        acme.people_set(identity, {"role": "admin"})
        acme.people_set(identity, {"role": "admin"}, meta={"$company_id": "other"})

        for _, message in self.consumer.log:
            assert message["$group_key"] == "$user_id"
            assert message["$group_id"] == "user_123"
            assert message["$company_id"] == "acme"

    def test_identity_company_wins_over_company_id_meta(self):
        self.hg.people_set(
            mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme"),
            {"role": "admin"},
            meta={"$company_id": "other"},
        )

        assert self.last_message()["$company_id"] == "acme"

    @pytest.mark.parametrize("company_id", [None, ""])
    def test_empty_company_id_meta_is_not_a_company(self, company_id):
        identity = mixpanel.MixpanelIdentity(user_id="user_123")
        with pytest.raises(mixpanel.CompanyRequiredError):
            self.hg.people_set(identity, {"a": 1}, meta={"$company_id": company_id})
        with pytest.raises(mixpanel.CompanyRequiredError):
            self.hg.group_set(
                "department", "finance", {"a": 1}, meta={"$company_id": company_id}
            )
        with pytest.raises(mixpanel.CompanyRequiredError):
            self.hg.group_update(
                {
                    "$group_key": "department",
                    "$group_id": "finance",
                    "$company_id": company_id,
                    "$set": {"a": 1},
                }
            )
        assert self.consumer.log == []

    def test_unsupported_operation_in_meta_is_rejected(self):
        identity = mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme")
        meta = {"$add": {"seats": 1}}
        error = mixpanel.UnsupportedOperationError
        with pytest.raises(error, match=re.escape("$add")):
            self.hg.for_company("acme").group_set(
                "department", "finance", {"a": 1}, meta=meta
            )
        with pytest.raises(error, match=re.escape("$add")):
            self.hg.for_company("acme").company_set({"a": 1}, meta=meta)
        with pytest.raises(error, match=re.escape("$add")):
            self.hg.people_set(identity, {"a": 1}, meta=meta)
        with pytest.raises(error, match=re.escape("$add")):
            self.hg.people_update(
                {"$distinct_id": self.COMBINED_ID, "$set": {"a": 1}}, meta=meta
            )
        assert self.consumer.log == []

    def test_unsupported_operation_in_meta_sent_without_hierarchical_groups(self):
        self.legacy.group_set(
            "department", "finance", {"a": 1}, meta={"$add": {"seats": 1}}
        )

        assert self.last_message()["$add"] == {"seats": 1}

    def test_legacy_identity_uses_engage(self):
        self.legacy.people_set(
            mixpanel.MixpanelIdentity(distinct_id="user_123"), {"role": "admin"}
        )

        endpoint, message = self.last()
        assert endpoint == "people"
        assert message["$distinct_id"] == "user_123"

    def test_combined_distinct_id_identity_profile_update_goes_to_groups(self):
        self.hg.people_set(
            mixpanel.MixpanelIdentity(distinct_id=self.COMBINED_ID), {"role": "admin"}
        )

        assert self.last() == (
            "groups",
            {
                "$token": self.TOKEN,
                "$time": 1000.1,
                "$group_key": "$user_id",
                "$group_id": "user_123",
                "$set": {"role": "admin"},
                "$company_id": "acme",
            },
        )

    def test_device_identity_cannot_identify_a_profile(self):
        identity = mixpanel.MixpanelIdentity(device_id="device_abc")

        with pytest.raises(ValueError, match="names no user"):
            self.hg.people_set(identity, {"plan": "pro"})
        with pytest.raises(ValueError, match="cannot identify a profile"):
            self.legacy.people_set(identity, {"plan": "pro"})
        assert self.consumer.log == []

    def test_company_only_identity_profile_update_is_rejected(self):
        with pytest.raises(ValueError, match="company_set") as excinfo:
            self.hg.people_set(
                mixpanel.MixpanelIdentity(company_id="acme"), {"tier": "ent"}
            )
        assert not isinstance(excinfo.value, mixpanel.CompanyRequiredError)

    # Group profiles

    def test_for_company_adds_top_level_company_id(self):
        self.hg.for_company("acme").group_set(
            "department", "finance", {"plan": "enterprise"}
        )

        message = self.last_message()
        assert message["$company_id"] == "acme"
        assert message["$group_key"] == "department"
        assert message["$group_id"] == "finance"
        assert "$company_id" not in message["$set"]

    def test_for_company_returns_a_new_client_sharing_the_consumer(self):
        acme = self.hg.for_company("acme")

        assert acme is not self.hg
        assert acme._consumer is self.hg._consumer
        assert acme._serializer is self.hg._serializer
        with pytest.raises(mixpanel.CompanyRequiredError):
            self.hg.group_set("department", "finance", {"plan": "x"})

    def test_user_and_company_profiles_have_bare_group_ids(self):
        acme = self.hg.for_company("acme")

        acme.group_set("$user_id", "user_123", {"role": "admin"})
        user = self.last_message()
        assert user["$group_key"] == "$user_id"
        assert user["$group_id"] == "user_123"
        assert user["$company_id"] == "acme"

        acme.group_set("$company_id", "acme", {"tier": "ent"})
        company = self.last_message()
        assert company["$group_key"] == "$company_id"
        assert company["$group_id"] == "acme"
        assert company["$company_id"] == "acme"

    def test_every_group_operation_carries_company(self):
        acme = self.hg.for_company("acme")
        acme.group_set("department", "finance", {"plan": "enterprise"})
        acme.group_set_once("department", "finance", {"plan": "enterprise"})
        acme.group_delete("department", "finance")
        acme.group_remove("department", "finance", {"tags": "a"})
        acme.group_union("department", "finance", {"tags": ["a"]})
        acme.group_unset("department", "finance", ["plan"])

        assert len(self.consumer.log) == 6
        for endpoint, message in self.consumer.log:
            assert endpoint == "groups"
            assert message["$company_id"] == "acme"

    def test_hierarchical_group_without_company_is_rejected(self):
        with pytest.raises(mixpanel.CompanyRequiredError, match="for_company"):
            self.hg.group_set("department", "finance", {"plan": "enterprise"})
        with pytest.raises(mixpanel.CompanyRequiredError, match="for_company"):
            self.hg.group_update(
                {"$group_key": "department", "$group_id": "finance", "$set": {}}
            )
        assert self.consumer.log == []

    @pytest.mark.parametrize("client", ["hg", "legacy"])
    def test_company_methods_match_group_methods(self, client):
        acme = getattr(self, client).for_company("acme")
        meta = {"$ip": "1.2.3.4", "$ignore_time": True}
        pairs = [
            (
                lambda: acme.company_set({"tier": "ent"}),
                lambda: acme.group_set("$company_id", "acme", {"tier": "ent"}),
            ),
            (
                lambda: acme.company_set({"tier": "ent"}, meta=meta),
                lambda: acme.group_set(
                    "$company_id", "acme", {"tier": "ent"}, meta=meta
                ),
            ),
            (
                lambda: acme.company_set_once({"first": "x"}, meta=meta),
                lambda: acme.group_set_once(
                    "$company_id", "acme", {"first": "x"}, meta=meta
                ),
            ),
            (
                lambda: acme.company_union({"tags": ["a"]}, meta=meta),
                lambda: acme.group_union(
                    "$company_id", "acme", {"tags": ["a"]}, meta=meta
                ),
            ),
            (
                lambda: acme.company_remove({"tags": "a"}),
                lambda: acme.group_remove("$company_id", "acme", {"tags": "a"}),
            ),
            (
                lambda: acme.company_unset(["tier", "plan"], meta=meta),
                lambda: acme.group_unset(
                    "$company_id", "acme", ["tier", "plan"], meta=meta
                ),
            ),
            (
                lambda: acme.company_unset(["tier"]),
                lambda: acme.group_unset("$company_id", "acme", ["tier"]),
            ),
            (
                lambda: acme.company_delete(meta=meta),
                lambda: acme.group_delete("$company_id", "acme", meta=meta),
            ),
            (
                acme.company_delete,
                lambda: acme.group_delete("$company_id", "acme"),
            ),
        ]
        for company_call, group_call in pairs:
            company_call()
            group_call()

        log = self.consumer.log
        assert len(log) == len(pairs) * 2
        for company, group in zip(log[::2], log[1::2]):
            assert company == group
            assert company[0] == "groups"
            assert company[1]["$group_key"] == "$company_id"
            assert company[1]["$group_id"] == "acme"
            assert company[1]["$company_id"] == "acme"

    @pytest.mark.parametrize("client", ["hg", "legacy"])
    def test_company_methods_require_a_bound_company(self, client):
        mp = getattr(self, client)
        calls = [
            lambda: mp.company_set({"tier": "ent"}),
            lambda: mp.company_set_once({"tier": "ent"}),
            lambda: mp.company_union({"tags": ["a"]}),
            lambda: mp.company_remove({"tags": "a"}),
            lambda: mp.company_unset(["tier"]),
            mp.company_delete,
        ]
        for call in calls:
            with pytest.raises(
                mixpanel.CompanyRequiredError,
                match=re.escape("for_company(company_id)"),
            ):
                call()
        assert self.consumer.log == []

    def test_company_methods_target_the_bound_company(self):
        self.hg.for_company("acme").for_company("other").company_set({"a": 1})

        message = self.last_message()
        assert message["$group_id"] == "other"
        assert message["$company_id"] == "other"

    def test_company_id_meta_is_accepted(self):
        self.hg.group_set(
            "department", "finance", {"plan": "x"}, meta={"$company_id": "acme"}
        )

        assert self.last_message()["$company_id"] == "acme"

    def test_for_company_wins_over_meta(self):
        self.hg.for_company("acme").group_set(
            "department", "finance", {"plan": "x"}, meta={"$company_id": "other"}
        )

        assert self.last_message()["$company_id"] == "acme"

    def test_legacy_group_unchanged(self):
        self.legacy.group_set("company", "Acme Inc.", {"plan": "x"})

        message = self.last_message()
        assert "$company_id" not in message
        assert message["$group_key"] == "company"

    def test_for_company_context_manager_keeps_shared_flag_providers_open(self):
        local, remote = MagicMock(), MagicMock()
        self.hg._local_flags_provider = local
        self.hg._remote_flags_provider = remote

        with self.hg.for_company("acme"):
            pass

        local.__exit__.assert_not_called()
        remote.__exit__.assert_not_called()

        with self.hg:
            pass

        local.__exit__.assert_called_once()
        remote.__exit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_for_company_async_context_manager_keeps_shared_flag_providers_open(
        self,
    ):
        local, remote = AsyncMock(), AsyncMock()
        self.hg._local_flags_provider = local
        self.hg._remote_flags_provider = remote

        async with self.hg.for_company("acme"):
            pass

        local.__aexit__.assert_not_called()
        remote.__aexit__.assert_not_called()

        async with self.hg:
            pass

        local.__aexit__.assert_called_once()
        remote.__aexit__.assert_called_once()

    def test_for_company_rejects_empty(self):
        with pytest.raises(ValueError, match="company_id"):
            self.hg.for_company("")
        with pytest.raises(ValueError, match="company_id"):
            self.hg.for_company(None)

    def test_for_company_accepts_integers_including_zero(self):
        for company_id in (0, 7):
            self.hg.for_company(company_id).company_set({"tier": "pro"})
            message = self.last_message()
            assert message["$company_id"] == str(company_id)
            assert message["$group_id"] == str(company_id)

    def test_for_company_rejects_other_types(self):
        for company_id in (True, False, 1.5, ["acme"], {"id": "acme"}):
            with pytest.raises(ValueError, match="company_id"):
                self.hg.for_company(company_id)

    def test_bound_company_compares_ids_as_strings(self):
        bound = self.hg.for_company(7)
        bound.people_set(
            mixpanel.MixpanelIdentity(user_id="user_123", company_id="7"), {"a": 1}
        )
        assert self.last_message()["$company_id"] == "7"
        bound.people_set("$company:7|$user:user_123", {"a": 1})
        assert self.last_message()["$company_id"] == "7"
        self.hg.for_company("7").people_set(
            mixpanel.MixpanelIdentity(user_id=1, company_id=7), {"a": 1}
        )
        assert self.last_message()["$company_id"] == "7"
        with pytest.raises(ValueError, match="bound to company 8"):
            self.hg.for_company(8).people_set(
                mixpanel.MixpanelIdentity(user_id=1, company_id=7), {"a": 1}
            )

    def test_people_update_allows_non_operation_keys(self):
        self.hg.people_update(
            {
                "$distinct_id": self.COMBINED_ID,
                "$company_id": "acme",
                "$group_key": "$user_id",
                "$group_id": "user_123",
                "$mp_metadata": {},
                "$set": {"plan": "pro"},
            }
        )

        endpoint, message = self.last()
        assert endpoint == "groups"
        assert message["$company_id"] == "acme"
        assert message["$group_id"] == "user_123"
        assert message["$set"] == {"plan": "pro"}
        assert "$distinct_id" not in message

    def test_user_profile_update_refuses_ignore_alias(self):
        # /groups rejects the whole record when it carries $ignore_alias.
        identity = mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme")
        for send in (
            lambda: self.hg.people_update(
                {
                    "$distinct_id": self.COMBINED_ID,
                    "$ignore_alias": True,
                    "$set": {"plan": "pro"},
                }
            ),
            lambda: self.hg.people_set(
                self.COMBINED_ID, {"plan": "pro"}, meta={"$ignore_alias": True}
            ),
            lambda: self.hg.people_set(
                identity, {"plan": "pro"}, meta={"$ignore_alias": False}
            ),
            lambda: self.hg.people_delete(identity, meta={"$ignore_alias": True}),
        ):
            with pytest.raises(ValueError, match=r"\$ignore_alias is not supported"):
                send()
        assert self.consumer.log == []

    def test_user_profile_meta_distinct_id_is_never_sent(self):
        # It names the target, so it is consumed rather than sent to /groups.
        identity = mixpanel.MixpanelIdentity(user_id="user_123", company_id="acme")
        self.hg.people_set(identity, {"plan": "pro"}, meta={"$distinct_id": None})
        self.hg.people_set(
            self.COMBINED_ID, {"plan": "pro"}, meta={"$distinct_id": self.COMBINED_ID}
        )

        for _endpoint, message in self.consumer.log:
            assert "$distinct_id" not in message
            assert message["$group_id"] == "user_123"

    def test_ignore_alias_without_hierarchical_groups_is_unchanged(self):
        self.legacy.people_set("user_123", {"a": 1}, meta={"$ignore_alias": True})
        self.legacy.group_update(
            {
                "$group_key": "company",
                "$group_id": "acme",
                "$distinct_id": "x",
                "$ignore_alias": True,
                "$set": {"a": 1},
            }
        )

        assert self.consumer.log[0][1]["$ignore_alias"] is True
        assert self.consumer.log[1][1]["$distinct_id"] == "x"
        assert self.consumer.log[1][1]["$ignore_alias"] is True

    def test_group_update_allows_non_operation_keys_and_refuses_others(self):
        acme = self.hg.for_company("acme")
        acme.group_update(
            {
                "$group_key": "company",
                "$group_id": "acme",
                "$mp_metadata": {},
                "$set": {"seats": 1},
            }
        )
        assert self.last_message()["$set"] == {"seats": 1}
        # /groups rejects the whole record when it carries either key.
        for key in ("$distinct_id", "$ignore_alias"):
            for message, meta in (
                ({key: "x"}, None),
                ({}, {key: "x"}),
            ):
                with pytest.raises(ValueError, match=rf"\{key} is not supported"):
                    acme.group_update(
                        {
                            "$group_key": "company",
                            "$group_id": "acme",
                            "$set": {"seats": 1},
                            **message,
                        },
                        meta=meta,
                    )
            with pytest.raises(ValueError, match=rf"\{key} is not supported"):
                acme.company_set({"seats": 1}, meta={key: "x"})
            with pytest.raises(ValueError, match=rf"\{key} is not supported"):
                self.hg.group_set(
                    "company", "acme", {"seats": 1}, meta={"$company_id": "a", key: 1}
                )
        assert len(self.consumer.log) == 1
        with pytest.raises(mixpanel.UnsupportedOperationError, match=r"\$foo"):
            acme.group_update({"$group_key": "company", "$group_id": "acme", "$foo": 1})
        with pytest.raises(mixpanel.UnsupportedOperationError, match=r"\$foo"):
            self.hg.people_update({"$distinct_id": self.COMBINED_ID, "$foo": 1})

    def test_for_company_keeps_add_and_append_rejected(self):
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.hg.for_company("acme").people_increment("user_123", {"logins": 1})

    def test_unsupported_group_operation_raises(self):
        for operation in ("$add", "$append", "$merge"):
            with pytest.raises(
                mixpanel.UnsupportedOperationError, match=re.escape(operation)
            ):
                self.hg.for_company("acme").group_update(
                    {
                        "$group_key": "company",
                        "$group_id": "acme",
                        operation: {"seats": 1},
                    }
                )
        assert self.consumer.log == []

    def test_unsupported_group_operation_raises_before_company_check(self):
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.hg.group_update(
                {"$group_key": "company", "$group_id": "acme", "$add": {"seats": 1}}
            )
        assert self.consumer.log == []

    def test_unsupported_group_operation_sent_without_hierarchical_groups(self):
        self.legacy.group_update(
            {"$group_key": "company", "$group_id": "acme", "$add": {"seats": 1}}
        )

        assert self.last_message()["$add"] == {"seats": 1}

    def test_supported_group_operations_are_sent(self, caplog):
        acme = self.hg.for_company("acme")
        acme.group_set("department", "finance", {"seats": 1})
        acme.group_set_once("department", "finance", {"seats": 1})
        acme.group_unset("department", "finance", ["seats"])
        acme.group_union("department", "finance", {"tags": ["a"]})
        acme.group_remove("department", "finance", {"seats": 1})
        acme.group_delete("department", "finance")
        acme.group_update(
            {"$group_key": "department", "$group_id": "finance", "$set": {"a": 1}},
            meta={"$ip": 0},
        )

        assert [r for r in caplog.records if r.levelname == "WARNING"] == []

    # Events and group profiles serialize identically in both modes

    def test_messages_valid_in_both_modes_are_byte_identical(self):
        def exercise(mp):
            mp.track("user_123", "Signup", {"plan": "pro"}, meta={"ip": 0})
            mp.import_data(None, "user_123", "Signup", 1000, {"plan": "pro"})
            mp.track(mixpanel.MixpanelIdentity(device_id="dev"), "Page View")
            mp.track(
                mixpanel.MixpanelIdentity(user_id="u", device_id="dev"), "Page View"
            )
            mp.group_set("company", "acme", {"plan": "x"}, meta={"$company_id": "a"})
            mp.for_company("acme").group_set("company", "acme", {"plan": "x"})
            mp.for_company("acme").group_delete("company", "acme")

        logs = []
        for hierarchical_groups in (False, True):
            consumer = RawConsumer()
            mp = mixpanel.Mixpanel(
                self.TOKEN, consumer=consumer, hierarchical_groups=hierarchical_groups
            )
            mp._now = lambda: 1000.1
            mp._make_insert_id = lambda: "abcdefg"
            exercise(mp)
            logs.append(consumer.log)

        assert len(logs[0]) == 7
        assert logs[0] == logs[1]

    def test_people_updates_go_to_engage_only_without_hierarchical_groups(self):
        identity = mixpanel.MixpanelIdentity(distinct_id="user_123")
        calls = []
        for profile in ("user_123", identity):
            calls += [
                lambda mp, p=profile: mp.people_set(p, {"plan": "pro"}, {"$ip": 0}),
                lambda mp, p=profile: mp.people_set_once(p, {"plan": "pro"}),
                lambda mp, p=profile: mp.people_union(p, {"tags": ["a"]}),
                lambda mp, p=profile: mp.people_unset(p, ["plan"]),
                lambda mp, p=profile: mp.people_remove(p, {"tags": "a"}),
                lambda mp, p=profile: mp.people_delete(p),
            ]
        calls.append(
            lambda mp: mp.people_update({"$distinct_id": "user_123", "$set": {}})
        )

        for call in calls:
            call(self.legacy)
            with pytest.raises(ValueError, match="need a user and a company"):
                call(self.hg)

        assert len(self.consumer.log) == len(calls)
        for endpoint, message in self.consumer.log:
            assert endpoint == "people"
            assert message["$distinct_id"] == "user_123"

    def test_unsupported_people_methods_unchanged_for_legacy(self):
        self.legacy.people_increment("user_123", {"logins": 1})
        self.legacy.people_append("user_123", {"items": "a"})
        self.legacy.people_track_charge("user_123", 9.99)
        self.legacy.people_update({"$distinct_id": "user_123", "$add": {"n": 1}})

        assert [message for _, message in self.consumer.log] == [
            {"$token": self.TOKEN, "$time": 1000.1, "$distinct_id": "user_123", **op}
            for op in (
                {"$add": {"logins": 1}},
                {"$append": {"items": "a"}},
                {"$append": {"$transactions": {"$amount": 9.99}}},
                {"$add": {"n": 1}},
            )
        ]


# Hierarchical groups scenarios

USER_ID = "my_user_id"
COMPANY_ID = "my_company_id"
TEAM_ID = "my_team_id"
DEVICE_ID = "my_device_id"
COMBINED_DISTINCT_ID = f"$company:{COMPANY_ID}|$user:{USER_ID}"
TOKEN = TestMixpanelBase.TOKEN
NOW = 1000.1
INSERT_ID = "abcdefg"


def make_client(consumer, *, hierarchical_groups=True):
    mp = mixpanel.Mixpanel(
        TOKEN, consumer=consumer, hierarchical_groups=hierarchical_groups
    )
    mp._now = lambda: NOW
    mp._make_insert_id = lambda: INSERT_ID
    return mp


def event_properties(**properties):
    return {
        "token": TOKEN,
        "time": NOW,
        "$insert_id": INSERT_ID,
        "mp_lib": "python",
        "$lib_version": mixpanel.__version__,
        **properties,
    }


def groups_message(group_key, group_id, operation, value):
    return {
        "$token": TOKEN,
        "$time": NOW,
        "$group_key": group_key,
        "$group_id": group_id,
        "$company_id": COMPANY_ID,
        operation: value,
    }


def user_update(operation, value):
    return groups_message("$user_id", USER_ID, operation, value)


def company_update(operation, value):
    return groups_message("$company_id", COMPANY_ID, operation, value)


def team_update(operation, value):
    return groups_message("team_id", TEAM_ID, operation, value)


class TestHierarchicalGroupsScenarios(TestMixpanelBase):
    """Hierarchical groups scenarios, one test per scenario.

    Each test locks the endpoint, the exact top-level keys of every ``/groups``
    message, the operation value, and the identity keys on events.
    """

    def setup_method(self):
        super().setup_method()
        self.mp = make_client(self.consumer)
        self.company = self.mp.for_company(COMPANY_ID)
        self.user = MixpanelIdentity(
            user_id=USER_ID, company_id=COMPANY_ID, device_id=DEVICE_ID
        )
        self.user_without_device = MixpanelIdentity(
            user_id=USER_ID, company_id=COMPANY_ID
        )

    def only_sent(self):
        assert len(self.consumer.log) == 1
        return self.consumer.log[0]

    def assert_only_event(self, event_name, properties, endpoint="events"):
        endpoint_sent, message = self.only_sent()
        assert endpoint_sent == endpoint
        assert message == {"event": event_name, "properties": properties}

    def assert_only_groups_update(self, expected):
        endpoint, message = self.only_sent()
        assert endpoint == "groups"
        assert message == expected
        assert set(message) == set(expected)

    def assert_nothing_sent(self):
        assert self.consumer.log == []

    # Events

    def test_track_anonymous(self):
        self.mp.track(MixpanelIdentity(device_id=DEVICE_ID), "Page View")

        self.assert_only_event(
            "Page View", event_properties(**{"$device_id": DEVICE_ID})
        )

    def test_track_identified(self):
        self.mp.track(self.user, "Signup")

        self.assert_only_event(
            "Signup",
            event_properties(
                **{
                    "$user_id": USER_ID,
                    "$company_id": COMPANY_ID,
                    "$device_id": DEVICE_ID,
                }
            ),
        )

    def test_track_identified_without_device(self):
        self.mp.track(self.user_without_device, "Signup")

        self.assert_only_event(
            "Signup",
            event_properties(**{"$user_id": USER_ID, "$company_id": COMPANY_ID}),
        )

    def test_track_with_custom_group(self):
        self.mp.track(self.user, "Signup", {"team_id": TEAM_ID})

        self.assert_only_event(
            "Signup",
            event_properties(
                **{
                    "team_id": TEAM_ID,
                    "$user_id": USER_ID,
                    "$company_id": COMPANY_ID,
                    "$device_id": DEVICE_ID,
                }
            ),
        )

    def test_import_identified(self):
        self.mp.import_data(None, self.user, "Signup", 1000)

        properties = event_properties(
            **{
                "time": 1000,
                "$user_id": USER_ID,
                "$company_id": COMPANY_ID,
                "$device_id": DEVICE_ID,
            }
        )
        self.assert_only_event("Signup", properties, endpoint="imports")

    def test_identity_overrides_properties(self):
        caller = {"$user_id": "other_user", "$company_id": "other_company"}

        self.mp.track(self.user, "Signup", caller)

        self.assert_only_event(
            "Signup",
            event_properties(
                **{
                    "$user_id": USER_ID,
                    "$company_id": COMPANY_ID,
                    "$device_id": DEVICE_ID,
                }
            ),
        )
        assert caller == {"$user_id": "other_user", "$company_id": "other_company"}

    def test_track_with_combined_distinct_id(self):
        self.mp.track(COMBINED_DISTINCT_ID, "Signup")

        self.assert_only_event(
            "Signup", event_properties(distinct_id=COMBINED_DISTINCT_ID)
        )

    def test_track_with_combined_distinct_id_identity(self):
        identity = mixpanel.MixpanelIdentity(distinct_id=COMBINED_DISTINCT_ID)

        self.mp.track(identity, "Signup")

        self.assert_only_event(
            "Signup", event_properties(distinct_id=COMBINED_DISTINCT_ID)
        )

    # User profile

    def test_set_user_property(self):
        self.mp.people_set(self.user, {"plan": "pro"})

        self.assert_only_groups_update(user_update("$set", {"plan": "pro"}))

    def test_set_user_property_with_combined_distinct_id(self):
        self.mp.people_set(COMBINED_DISTINCT_ID, {"plan": "pro"})

        self.assert_only_groups_update(user_update("$set", {"plan": "pro"}))

    def test_set_user_property_with_combined_distinct_id_identity(self):
        identity = MixpanelIdentity(distinct_id=COMBINED_DISTINCT_ID)

        self.mp.people_set(identity, {"plan": "pro"})

        self.assert_only_groups_update(user_update("$set", {"plan": "pro"}))

    def test_set_user_property_with_distinct_id_is_unsupported(self):
        with pytest.raises(ValueError, match="need a user and a company"):
            self.mp.people_set(USER_ID, {"plan": "pro"})

        self.assert_nothing_sent()

    def test_set_user_properties(self):
        self.mp.people_set(self.user, {"plan": "pro", "seats": 5})

        self.assert_only_groups_update(user_update("$set", {"plan": "pro", "seats": 5}))

    def test_set_once_user_property(self):
        self.mp.people_set_once(self.user, {"first_seen": "today"})

        self.assert_only_groups_update(
            user_update("$set_once", {"first_seen": "today"})
        )

    def test_union_user_property(self):
        self.mp.people_union(self.user, {"tags": ["a", "b"]})

        self.assert_only_groups_update(user_update("$union", {"tags": ["a", "b"]}))

    def test_remove_user_property(self):
        self.mp.people_remove(self.user, {"tags": "a"})

        self.assert_only_groups_update(user_update("$remove", {"tags": "a"}))

    def test_unset_user_property(self):
        self.mp.people_unset(self.user, ["plan"])

        self.assert_only_groups_update(user_update("$unset", ["plan"]))

    def test_delete_user(self):
        self.mp.people_delete(self.user)

        self.assert_only_groups_update(user_update("$delete", ""))

    def test_clear_charges_is_unsupported(self):
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.mp.people_clear_charges(self.user)
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.mp.people_clear_charges(USER_ID)

        self.assert_nothing_sent()

    def test_increment_user_property_is_unsupported(self):
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.mp.people_increment(self.user, {"logins": 1})
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.mp.people_increment(USER_ID, {"logins": 1, "sessions": 2})

        self.assert_nothing_sent()

    def test_append_user_property_is_unsupported(self):
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.mp.people_append(self.user, {"items": "a"})
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.mp.people_append(USER_ID, {"items": "a"})

        self.assert_nothing_sent()

    def test_track_charge_is_unsupported(self):
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.mp.people_track_charge(self.user, 9.99)
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.mp.people_track_charge(USER_ID, 9.99, {"sku": "a"})

        self.assert_nothing_sent()

    # Company

    def test_set_company_property(self):
        self.company.group_set("$company_id", COMPANY_ID, {"tier": "enterprise"})

        self.assert_only_groups_update(company_update("$set", {"tier": "enterprise"}))

    def test_set_company_properties(self):
        self.company.group_set(
            "$company_id", COMPANY_ID, {"tier": "enterprise", "seats": 100}
        )

        self.assert_only_groups_update(
            company_update("$set", {"tier": "enterprise", "seats": 100})
        )

    def test_set_once_company_property(self):
        self.company.group_set_once("$company_id", COMPANY_ID, {"founded": 2001})

        self.assert_only_groups_update(company_update("$set_once", {"founded": 2001}))

    def test_union_company_property(self):
        self.company.group_union("$company_id", COMPANY_ID, {"regions": ["eu"]})

        self.assert_only_groups_update(company_update("$union", {"regions": ["eu"]}))

    def test_remove_company_property(self):
        self.company.group_remove("$company_id", COMPANY_ID, {"regions": "eu"})

        self.assert_only_groups_update(company_update("$remove", {"regions": "eu"}))

    def test_unset_company_property(self):
        self.company.group_unset("$company_id", COMPANY_ID, ["tier"])

        self.assert_only_groups_update(company_update("$unset", ["tier"]))

    # Custom groups

    def test_set_users_custom_group(self):
        self.company.people_set(self.user, {"team_id": TEAM_ID})

        self.assert_only_groups_update(user_update("$set", {"team_id": TEAM_ID}))

    def test_remove_users_custom_group(self):
        self.company.people_unset(self.user, ["team_id"])

        self.assert_only_groups_update(user_update("$unset", ["team_id"]))

    def test_set_custom_group_property(self):
        self.company.group_set("team_id", TEAM_ID, {"name": "Core"})

        self.assert_only_groups_update(team_update("$set", {"name": "Core"}))

    def test_set_custom_group_properties(self):
        self.company.group_set("team_id", TEAM_ID, {"name": "Core", "size": 8})

        self.assert_only_groups_update(team_update("$set", {"name": "Core", "size": 8}))

    def test_set_once_custom_group_property(self):
        self.company.group_set_once("team_id", TEAM_ID, {"formed": 2020})

        self.assert_only_groups_update(team_update("$set_once", {"formed": 2020}))

    def test_union_custom_group_property(self):
        self.company.group_union("team_id", TEAM_ID, {"tools": ["git"]})

        self.assert_only_groups_update(team_update("$union", {"tools": ["git"]}))

    def test_remove_custom_group_property(self):
        self.company.group_remove("team_id", TEAM_ID, {"tools": "git"})

        self.assert_only_groups_update(team_update("$remove", {"tools": "git"}))

    def test_unset_custom_group_property(self):
        self.company.group_unset("team_id", TEAM_ID, ["name"])

        self.assert_only_groups_update(team_update("$unset", ["name"]))

    def test_delete_company(self):
        self.company.group_delete("$company_id", COMPANY_ID)

        self.assert_only_groups_update(company_update("$delete", ""))

    def test_delete_custom_group(self):
        self.company.group_delete("team_id", TEAM_ID)

        self.assert_only_groups_update(team_update("$delete", ""))

    # Company group id must match the company

    @pytest.mark.parametrize(
        "update",
        [
            lambda mp: mp.group_set("$company_id", "globex", {"plan": "pro"}),
            lambda mp: mp.group_set_once("$company_id", "globex", {"plan": "pro"}),
            lambda mp: mp.group_union("$company_id", "globex", {"regions": ["eu"]}),
            lambda mp: mp.group_unset("$company_id", "globex", ["plan"]),
            lambda mp: mp.group_remove("$company_id", "globex", {"regions": "eu"}),
            lambda mp: mp.group_delete("$company_id", "globex"),
        ],
    )
    def test_company_group_with_other_company_id_is_rejected(self, update):
        with pytest.raises(ValueError, match="globex") as error:
            update(self.company)

        assert type(error.value) is ValueError
        assert COMPANY_ID in str(error.value)
        self.assert_nothing_sent()

    def test_company_group_with_other_meta_company_is_rejected(self):
        with pytest.raises(ValueError, match="globex") as error:
            self.mp.group_set(
                "$company_id", "globex", {"plan": "pro"}, meta={"$company_id": "acme"}
            )

        assert type(error.value) is ValueError
        assert "acme" in str(error.value)
        self.assert_nothing_sent()

    def test_company_group_update_with_other_company_id_is_rejected(self):
        message = {"$group_key": "$company_id", "$group_id": "globex", "$set": {}}

        with pytest.raises(ValueError, match="globex"):
            self.company.group_update(message)
        with pytest.raises(ValueError, match="globex"):
            self.mp.group_update({**message, "$company_id": "acme"})
        with pytest.raises(ValueError, match="globex"):
            self.mp.group_update(message, meta={"$company_id": "acme"})

        self.assert_nothing_sent()

    def test_company_group_with_matching_company_id_is_sent(self):
        self.company.group_set("$company_id", COMPANY_ID, {"plan": "pro"})
        self.company.company_set({"plan": "pro"})

        assert self.consumer.log == [
            ("groups", company_update("$set", {"plan": "pro"})),
            ("groups", company_update("$set", {"plan": "pro"})),
        ]

    def test_company_group_compares_ids_as_strings(self):
        self.mp.for_company(7).group_set("$company_id", "7", {"plan": "pro"})
        self.mp.for_company("7").group_set("$company_id", 7, {"plan": "pro"})

        assert self.consumer.log == [
            (
                "groups",
                {
                    "$token": TOKEN,
                    "$time": NOW,
                    "$group_key": "$company_id",
                    "$group_id": "7",
                    "$company_id": "7",
                    "$set": {"plan": "pro"},
                },
            ),
            (
                "groups",
                {
                    "$token": TOKEN,
                    "$time": NOW,
                    "$group_key": "$company_id",
                    "$group_id": 7,
                    "$company_id": "7",
                    "$set": {"plan": "pro"},
                },
            ),
        ]

    # $company_id in meta or the message must be a non-blank string or integer

    @pytest.mark.parametrize("company", [{"x": 1}, True, 1.5, ["acme"], " ", "  "])
    def test_invalid_meta_company_id_is_rejected(self, company):
        with pytest.raises(ValueError, match=r"\$company_id must be") as error:
            self.mp.group_set(
                "team_id", TEAM_ID, {"name": "Core"}, meta={"$company_id": company}
            )
        assert type(error.value) is ValueError
        with pytest.raises(ValueError, match=r"\$company_id must be"):
            self.mp.group_update(
                {
                    "$group_key": "team_id",
                    "$group_id": TEAM_ID,
                    "$set": {},
                    "$company_id": company,
                }
            )
        with pytest.raises(ValueError, match=r"\$company_id must be"):
            self.mp.people_set(
                MixpanelIdentity(user_id=USER_ID),
                {"plan": "pro"},
                meta={"$company_id": company},
            )

        self.assert_nothing_sent()

    def test_empty_meta_company_id_counts_as_missing(self):
        with pytest.raises(mixpanel.CompanyRequiredError):
            self.mp.group_set(
                "team_id", TEAM_ID, {"name": "Core"}, meta={"$company_id": ""}
            )

        self.assert_nothing_sent()

    def test_valid_meta_company_id_is_sent_unchanged(self):
        self.mp.group_set(
            "team_id", TEAM_ID, {"name": "Core"}, meta={"$company_id": COMPANY_ID}
        )
        self.mp.group_set("team_id", TEAM_ID, {"name": "Core"}, meta={"$company_id": 7})

        assert self.consumer.log == [
            ("groups", team_update("$set", {"name": "Core"})),
            ("groups", {**team_update("$set", {"name": "Core"}), "$company_id": 7}),
        ]

    def test_invalid_meta_company_id_without_hierarchical_groups(self):
        mp = make_client(self.consumer, hierarchical_groups=False)

        mp.group_set(
            "team_id", TEAM_ID, {"name": "Core"}, meta={"$company_id": {"x": 1}}
        )
        mp.group_set("team_id", TEAM_ID, {"name": "Core"}, meta={"$company_id": " "})

        assert self.consumer.log == [
            (
                "groups",
                {**team_update("$set", {"name": "Core"}), "$company_id": {"x": 1}},
            ),
            ("groups", {**team_update("$set", {"name": "Core"}), "$company_id": " "}),
        ]

    # Integer ids are sent as strings

    def test_integer_identity_ids_are_sent_as_strings_on_events(self):
        identity = MixpanelIdentity(user_id=3190316, company_id=3190317, device_id=5)

        self.mp.track(identity, "Signup", {"count": 3, "$company_id": "ignored"})

        self.assert_only_event(
            "Signup",
            event_properties(
                **{
                    "count": 3,
                    "$user_id": "3190316",
                    "$company_id": "3190317",
                    "$device_id": "5",
                }
            ),
        )

    def test_integer_identity_ids_are_sent_as_strings_on_profiles(self):
        self.mp.people_set(
            MixpanelIdentity(user_id=3190316, company_id=3190317), {"plan": "pro"}
        )
        self.mp.for_company(3190317).people_set(
            MixpanelIdentity(user_id=3190316), {"plan": "pro"}
        )

        expected = {
            "$token": TOKEN,
            "$time": NOW,
            "$group_key": "$user_id",
            "$group_id": "3190316",
            "$company_id": "3190317",
            "$set": {"plan": "pro"},
        }
        assert self.consumer.log == [("groups", expected), ("groups", expected)]

    def test_integer_bound_company_is_sent_as_string(self):
        company = self.mp.for_company(7)

        company.company_set({"plan": "pro"})
        company.group_set("team_id", 9, {"name": "Core"})

        assert self.consumer.log == [
            (
                "groups",
                {
                    "$token": TOKEN,
                    "$time": NOW,
                    "$group_key": "$company_id",
                    "$group_id": "7",
                    "$company_id": "7",
                    "$set": {"plan": "pro"},
                },
            ),
            (
                "groups",
                {
                    "$token": TOKEN,
                    "$time": NOW,
                    "$group_key": "team_id",
                    "$group_id": 9,
                    "$company_id": "7",
                    "$set": {"name": "Core"},
                },
            ),
        ]

    def test_integer_ids_without_hierarchical_groups(self):
        mp = make_client(self.consumer, hierarchical_groups=False)

        mp.track(MixpanelIdentity(user_id=42, device_id=5), "Signup")
        mp.for_company(7).company_set({"plan": "pro"})

        assert self.consumer.log == [
            (
                "events",
                {
                    "event": "Signup",
                    "properties": event_properties(
                        **{"$user_id": "42", "$device_id": "5"}
                    ),
                },
            ),
            (
                "groups",
                {
                    "$token": TOKEN,
                    "$time": NOW,
                    "$group_key": "$company_id",
                    "$group_id": "7",
                    "$company_id": "7",
                    "$set": {"plan": "pro"},
                },
            ),
        ]

    # A combined distinct id must agree with the event's $company_id / $user_id

    @pytest.mark.parametrize(
        ("properties", "message"),
        [
            (
                {"$company_id": "zz6"},
                "distinct_id '$company:c6|$user:u6' names company 'c6', "
                "but $company_id is 'zz6'. Nothing sent",
            ),
            (
                {"$user_id": "zz6"},
                "distinct_id '$company:c6|$user:u6' names user 'u6', "
                "but $user_id is 'zz6'. Nothing sent",
            ),
        ],
    )
    def test_event_conflicting_with_combined_distinct_id_is_rejected(
        self, properties, message
    ):
        with pytest.raises(ValueError, match="names") as error:
            self.mp.track("$company:c6|$user:u6", "Signup", properties)
        assert str(error.value) == message
        with pytest.raises(ValueError, match="names"):
            self.mp.import_data(None, "$company:c6|$user:u6", "Signup", 1, properties)

        self.assert_nothing_sent()

    def test_event_matching_combined_distinct_id_is_sent_unchanged(self):
        self.mp.track(
            "$company:7|$user:8", "Signup", {"$company_id": 7, "$user_id": "8"}
        )

        self.assert_only_event(
            "Signup",
            event_properties(
                **{
                    "distinct_id": "$company:7|$user:8",
                    "$company_id": 7,
                    "$user_id": "8",
                }
            ),
        )

    def test_event_with_plain_distinct_id_and_company_is_sent_unchanged(self):
        self.mp.track(USER_ID, "Signup", {"$company_id": "zz6"})

        self.assert_only_event(
            "Signup", event_properties(**{"distinct_id": USER_ID, "$company_id": "zz6"})
        )

    def test_event_conflicting_with_combined_distinct_id_without_hierarchical_groups(
        self,
    ):
        mp = make_client(self.consumer, hierarchical_groups=False)

        mp.track("$company:c6|$user:u6", "Signup", {"$company_id": "zz6"})

        self.assert_only_event(
            "Signup",
            event_properties(
                **{"distinct_id": "$company:c6|$user:u6", "$company_id": "zz6"}
            ),
        )

    def test_profile_conflicting_with_combined_distinct_id_is_rejected(self):
        with pytest.raises(ValueError, match="names") as error:
            self.mp.people_set(
                "$company:c6|$user:u6", {"plan": "pro"}, meta={"$company_id": "zz6"}
            )

        assert str(error.value) == (
            "distinct_id '$company:c6|$user:u6' names company 'c6', "
            "but $company_id is 'zz6'. Nothing sent"
        )
        self.assert_nothing_sent()

    # Whitespace-only ids

    @pytest.mark.parametrize("hierarchical_groups", [True, False])
    @pytest.mark.parametrize("blank", [" ", "  ", "\t"])
    def test_blank_identity_and_bound_company_are_rejected(
        self, hierarchical_groups, blank
    ):
        mp = make_client(self.consumer, hierarchical_groups=hierarchical_groups)

        with pytest.raises(ValueError, match="user_id"):
            MixpanelIdentity(user_id=blank)
        with pytest.raises(ValueError, match="company_id"):
            MixpanelIdentity(user_id=USER_ID, company_id=blank)
        with pytest.raises(ValueError, match="company_id"):
            mp.for_company(blank)

    @pytest.mark.parametrize(
        ("distinct_id", "part"),
        [
            ("$company: |$user:", "company"),
            ("$company: |$user:u", "company"),
            ("$company:c|$user:  ", "user"),
            ("$company:|$user:u", "company"),
            ("$company:c|$user:", "user"),
            ("$company:|$user:", "company"),
        ],
    )
    def test_blank_combined_distinct_id_is_rejected(self, distinct_id, part):
        message = f"distinct_id {distinct_id!r} names a blank {part}. Nothing sent"
        for send in (
            lambda: self.mp.track(distinct_id, "Signup"),
            lambda: self.mp.import_data(None, distinct_id, "Signup", 1000),
            lambda: self.mp.people_set(distinct_id, {"plan": "pro"}),
            lambda: self.mp.people_update({"$distinct_id": distinct_id, "$set": {}}),
        ):
            with pytest.raises(ValueError, match="names a blank") as error:
                send()
            assert str(error.value) == message

        self.assert_nothing_sent()

    @pytest.mark.parametrize(
        ("distinct_id", "part"),
        [
            ("$company: |$user:", "company"),
            ("$company: |$user:u", "company"),
            ("$company:c|$user:  ", "user"),
            ("$company:|$user:u", "company"),
            ("$company:c|$user:", "user"),
            ("$company:|$user:", "company"),
        ],
    )
    def test_identity_with_blank_combined_distinct_id_is_rejected(
        self, distinct_id, part
    ):
        message = f"distinct_id {distinct_id!r} names a blank {part}. Nothing sent"
        identity = MixpanelIdentity(
            distinct_id=distinct_id, user_id=USER_ID, company_id=COMPANY_ID
        )
        for send in (
            lambda: self.mp.track(identity, "Signup"),
            lambda: self.mp.import_data(None, identity, "Signup", 1000),
        ):
            with pytest.raises(ValueError, match="names a blank") as error:
                send()
            assert str(error.value) == message

        self.assert_nothing_sent()

    def test_identity_with_valid_combined_distinct_id_is_sent(self):
        identity = MixpanelIdentity(
            distinct_id=COMBINED_DISTINCT_ID, user_id=USER_ID, company_id=COMPANY_ID
        )

        self.mp.track(identity, "Signup")

        self.assert_only_event(
            "Signup",
            event_properties(
                distinct_id=COMBINED_DISTINCT_ID,
                **{"$user_id": USER_ID, "$company_id": COMPANY_ID},
            ),
        )

    @pytest.mark.parametrize(
        ("identity", "message"),
        [
            (
                MixpanelIdentity(
                    distinct_id="$company:acme|$user:old",
                    user_id="new",
                    company_id="acme",
                ),
                "distinct_id '$company:acme|$user:old' names user 'old', but "
                "user_id is 'new'. Nothing sent",
            ),
            (
                MixpanelIdentity(
                    distinct_id="$company:acme|$user:u1",
                    user_id="u1",
                    company_id="other",
                ),
                "distinct_id '$company:acme|$user:u1' names company 'acme', but "
                "company_id is 'other'. Nothing sent",
            ),
            (
                MixpanelIdentity(distinct_id="$company:acme|$user:old", user_id="new"),
                "distinct_id '$company:acme|$user:old' names user 'old', but "
                "user_id is 'new'. Nothing sent",
            ),
            (
                MixpanelIdentity(distinct_id="$company:1|$user:2", company_id=3),
                "distinct_id '$company:1|$user:2' names company '1', but "
                "company_id is 3. Nothing sent",
            ),
        ],
    )
    def test_identity_whose_combined_distinct_id_disagrees_is_rejected(
        self, identity, message
    ):
        for send in (
            lambda: self.mp.track(identity, "Signup"),
            lambda: self.mp.import_data(None, identity, "Signup", 1000),
            lambda: self.mp.people_set(identity, {"plan": "pro"}),
            lambda: self.mp.people_set_once(identity, {"plan": "pro"}),
            lambda: self.mp.people_unset(identity, ["plan"]),
            lambda: self.mp.people_union(identity, {"tags": ["a"]}),
            lambda: self.mp.people_remove(identity, {"tags": "a"}),
            lambda: self.mp.people_delete(identity),
        ):
            with pytest.raises(ValueError, match="Nothing sent") as error:
                send()
            assert str(error.value) == message

        self.assert_nothing_sent()

    def test_identity_whose_combined_distinct_id_agrees_is_sent(self):
        identity = MixpanelIdentity(
            distinct_id="$company:42|$user:7", user_id=7, company_id=42
        )

        self.mp.track(identity, "Signup")
        self.mp.people_delete(identity)

        assert self.consumer.log == [
            (
                "events",
                {
                    "event": "Signup",
                    "properties": event_properties(
                        distinct_id="$company:42|$user:7",
                        **{"$user_id": "7", "$company_id": "42"},
                    ),
                },
            ),
            (
                "groups",
                {
                    "$token": TOKEN,
                    "$time": NOW,
                    "$group_key": "$user_id",
                    "$group_id": "7",
                    "$company_id": "42",
                    "$delete": "",
                },
            ),
        ]

    def test_identity_whose_combined_distinct_id_disagrees_without_hierarchical_groups(
        self,
    ):
        mp = make_client(self.consumer, hierarchical_groups=False)
        identity = MixpanelIdentity(
            distinct_id="$company:acme|$user:old", user_id="new"
        )

        mp.track(identity, "Signup")
        mp.people_delete(identity)

        assert self.consumer.log == [
            (
                "events",
                {
                    "event": "Signup",
                    "properties": event_properties(
                        distinct_id="$company:acme|$user:old", **{"$user_id": "new"}
                    ),
                },
            ),
            (
                "people",
                {
                    "$token": TOKEN,
                    "$time": NOW,
                    "$distinct_id": "$company:acme|$user:old",
                    "$delete": "",
                },
            ),
        ]

    @pytest.mark.parametrize(
        "distinct_id", ["$company: |$user:", "$company:|$user:u", "$company:c|$user:"]
    )
    def test_identity_with_blank_combined_distinct_id_without_hierarchical_groups(
        self, distinct_id
    ):
        mp = make_client(self.consumer, hierarchical_groups=False)

        mp.track(MixpanelIdentity(distinct_id=distinct_id), "Signup")

        self.assert_only_event("Signup", event_properties(distinct_id=distinct_id))

    @pytest.mark.parametrize(
        "distinct_id", ["$company:|$user:u", "$company:c|$user:", "$company: |$user:u"]
    )
    def test_exposure_with_blank_combined_distinct_id_is_dropped(self, distinct_id):
        context = {
            "distinct_id": distinct_id,
            "$user_id": USER_ID,
            "$company_id": COMPANY_ID,
        }

        assert exposure_identity(context, True) is None

    @pytest.mark.parametrize(
        "distinct_id", ["user_123", "$device:abc", "$company:acme"]
    )
    def test_non_combined_distinct_id_is_sent_as_given(self, distinct_id):
        self.mp.track(distinct_id, "Signup")

        self.assert_only_event("Signup", event_properties(distinct_id=distinct_id))

    @pytest.mark.parametrize(
        "distinct_id", ["$company: |$user:", "$company:|$user:u", "$company:c|$user:"]
    )
    def test_blank_combined_distinct_id_without_hierarchical_groups(self, distinct_id):
        mp = make_client(self.consumer, hierarchical_groups=False)

        mp.track(distinct_id, "Signup")

        self.assert_only_event("Signup", event_properties(distinct_id=distinct_id))

    def test_ids_with_surrounding_spaces_are_sent_unchanged(self):
        self.mp.track(MixpanelIdentity(user_id=" u ", company_id=" c "), "Signup")
        self.mp.track("$company: c |$user: u ", "Signup")

        assert [message["properties"] for _, message in self.consumer.log] == [
            event_properties(**{"$user_id": " u ", "$company_id": " c "}),
            event_properties(distinct_id="$company: c |$user: u "),
        ]

    # "|" in user and company ids

    @pytest.mark.parametrize(
        ("identity", "name"),
        [
            (MixpanelIdentity(user_id="u|1", company_id=COMPANY_ID), "user_id"),
            (MixpanelIdentity(user_id=USER_ID, company_id="c|1"), "company_id"),
            (MixpanelIdentity(user_id="u|1"), "user_id"),
            (MixpanelIdentity(company_id="c|1"), "company_id"),
        ],
    )
    def test_identity_with_pipe_is_rejected(self, identity, name):
        message = f"{name} must not contain '|' on a hierarchical groups project"
        for send in (
            lambda: self.mp.track(identity, "Signup"),
            lambda: self.mp.import_data(None, identity, "Signup", 1000),
            lambda: self.mp.people_set(identity, {"plan": "pro"}),
            lambda: self.mp.people_delete(identity),
        ):
            with pytest.raises(ValueError, match=re.escape(message)):
                send()

        self.assert_nothing_sent()

    def test_company_with_pipe_is_rejected(self):
        message = "must not contain '|' on a hierarchical groups project"
        with pytest.raises(ValueError, match=f"company_id {message}"):
            self.mp.for_company("c|1")
        for meta in ({"$company_id": "c|1"}, {"$company_id": "c|"}):
            with pytest.raises(ValueError, match=re.escape(f"$company_id {message}")):
                self.mp.group_set(TEAM_ID, "t", {"name": "Core"}, meta=meta)
            with pytest.raises(ValueError, match=re.escape(f"$company_id {message}")):
                self.mp.people_set(
                    MixpanelIdentity(user_id=USER_ID), {"plan": "pro"}, meta=meta
                )
        with pytest.raises(ValueError, match=re.escape(f"$company_id {message}")):
            self.mp.group_update(
                {
                    "$group_key": "team_id",
                    "$group_id": "t",
                    "$company_id": "c|1",
                    "$set": {},
                }
            )

        self.assert_nothing_sent()

    def test_pipe_in_custom_group_id_and_raw_properties_is_sent(self):
        self.company.group_set("team_id", "t|1", {"name": "Core"})
        self.mp.track(self.user, "Signup", {"note": "a|b"})

        assert [message for _, message in self.consumer.log] == [
            {
                **team_update("$set", {"name": "Core"}),
                "$group_id": "t|1",
            },
            {
                "event": "Signup",
                "properties": event_properties(
                    **{
                        "note": "a|b",
                        "$user_id": USER_ID,
                        "$company_id": COMPANY_ID,
                        "$device_id": DEVICE_ID,
                    }
                ),
            },
        ]

    def test_pipe_in_ids_without_hierarchical_groups_is_sent(self):
        mp = make_client(self.consumer, hierarchical_groups=False)

        mp.track(MixpanelIdentity(user_id="u|1", device_id="d|1"), "Signup")
        mp.for_company("c|1").company_set({"plan": "pro"})

        assert [message for _, message in self.consumer.log] == [
            {
                "event": "Signup",
                "properties": event_properties(
                    **{"$user_id": "u|1", "$device_id": "d|1"}
                ),
            },
            {
                "$token": TOKEN,
                "$time": NOW,
                "$group_key": "$company_id",
                "$group_id": "c|1",
                "$company_id": "c|1",
                "$set": {"plan": "pro"},
            },
        ]

    @pytest.mark.parametrize(
        "context",
        [
            {"$user_id": "u|1", "$company_id": COMPANY_ID},
            {"$user_id": USER_ID, "$company_id": "c|1"},
            {"distinct_id": "$company:a|b|$user:u"},
        ],
    )
    def test_exposure_with_pipe_in_ids_is_dropped(self, context):
        assert exposure_identity(context, True) is None

    def test_blank_exposure_company_counts_as_missing(self):
        assert (
            exposure_identity({"$company_id": " ", "$user_id": USER_ID}, True) is None
        )
        assert exposure_identity(
            {"$company_id": COMPANY_ID, "$user_id": " "}, True
        ) == MixpanelIdentity(company_id=COMPANY_ID)

    # Unsupported / rejected

    def test_identify_without_company(self):
        identity = MixpanelIdentity(user_id=USER_ID)

        # The event is sent as given; a user profile needs the company.
        with pytest.raises(mixpanel.CompanyRequiredError):
            self.mp.people_set(identity, {"plan": "pro"})
        self.assert_nothing_sent()

        self.mp.track(identity, "Signup")
        endpoint, message = self.only_sent()
        assert endpoint == "events"
        assert message["properties"]["$user_id"] == USER_ID
        assert "$company_id" not in message["properties"]

    def test_set_user_property_without_user(self):
        with pytest.raises(ValueError, match="require a user id"):
            self.mp.people_set(MixpanelIdentity(company_id=COMPANY_ID), {"plan": "pro"})

        self.assert_nothing_sent()

    def test_set_company_property_without_company(self):
        with pytest.raises(mixpanel.CompanyRequiredError):
            self.mp.group_set("$company_id", COMPANY_ID, {"tier": "enterprise"})

        self.assert_nothing_sent()

    def test_set_custom_group_property_without_company(self):
        with pytest.raises(mixpanel.CompanyRequiredError):
            self.mp.group_set("team_id", TEAM_ID, {"name": "Core"})

        self.assert_nothing_sent()

    def test_company_identity_without_hierarchical_groups(self):
        mp = make_client(self.consumer, hierarchical_groups=False)

        with pytest.raises(ValueError, match="hierarchical_groups=True"):
            mp.track(self.user, "Signup")
        with pytest.raises(ValueError, match="hierarchical_groups=True"):
            mp.people_set(self.user, {"plan": "pro"})
        with pytest.raises(ValueError, match="hierarchical_groups=True"):
            mp.track(MixpanelIdentity(company_id=COMPANY_ID), "Renewed")

        self.assert_nothing_sent()

    def test_alias(self):
        # A user is identified by company and user id, so there is nothing to alias.
        with responses.RequestsMock() as rsps:
            with pytest.raises(mixpanel.UnsupportedOperationError):
                self.mp.alias("new_alias", USER_ID)
            assert len(rsps.calls) == 0
        self.assert_nothing_sent()

    def test_merge(self):
        # A user is identified by company and user id, so there is nothing to merge.
        with pytest.raises(mixpanel.UnsupportedOperationError):
            self.mp.merge(None, USER_ID, DEVICE_ID)
        self.assert_nothing_sent()

    # Without hierarchical groups

    def test_track_with_distinct_id(self):
        mp = make_client(self.consumer, hierarchical_groups=False)

        mp.track(USER_ID, "Signup")

        self.assert_only_event("Signup", event_properties(distinct_id=USER_ID))

    def test_set_user_property_with_distinct_id(self):
        mp = make_client(self.consumer, hierarchical_groups=False)

        mp.people_set(USER_ID, {"plan": "pro"})

        endpoint, message = self.only_sent()
        assert endpoint == "people"
        assert message == {
            "$token": TOKEN,
            "$time": NOW,
            "$distinct_id": USER_ID,
            "$set": {"plan": "pro"},
        }

    def test_company_group_with_other_company_id_without_hierarchical_groups(self):
        mp = make_client(self.consumer, hierarchical_groups=False)

        mp.for_company("acme").group_set("$company_id", "globex", {"plan": "pro"})

        endpoint, message = self.only_sent()
        assert endpoint == "groups"
        assert message == {
            "$token": TOKEN,
            "$time": NOW,
            "$group_key": "$company_id",
            "$group_id": "globex",
            "$company_id": "acme",
            "$set": {"plan": "pro"},
        }

    def test_set_group_property(self):
        mp = make_client(self.consumer, hierarchical_groups=False)

        mp.group_set("team_id", TEAM_ID, {"name": "Core"})

        endpoint, message = self.only_sent()
        assert endpoint == "groups"
        assert message == {
            "$token": TOKEN,
            "$time": NOW,
            "$group_key": "team_id",
            "$group_id": TEAM_ID,
            "$set": {"name": "Core"},
        }

    # meta may repeat, but never retarget, a hierarchical groups update

    def test_meta_that_retargets_an_update_is_rejected(self):
        same = MixpanelIdentity(user_id="acme", company_id="acme")
        combined = COMBINED_DISTINCT_ID
        identity = MixpanelIdentity(distinct_id=combined, company_id=COMPANY_ID)
        for send, message in (
            (
                lambda: self.mp.people_set(
                    self.user, {"plan": "pro"}, meta={"$group_id": "u2"}
                ),
                f"meta $group_id is 'u2', but the message's $group_id is "
                f"{USER_ID!r}. Nothing sent",
            ),
            (
                lambda: self.mp.people_set(
                    self.user, {"plan": "pro"}, meta={"$token": "other"}
                ),
                "meta $token is 'other', but this client's token differs. Nothing sent",
            ),
            (
                lambda: self.mp.people_delete(same, meta={"$group_key": "$company_id"}),
                "meta $group_key is '$company_id', but the message's $group_key "
                "is '$user_id'. Nothing sent",
            ),
            (
                lambda: self.company.group_set(
                    "dept", "fin", {"x": 1}, meta={"$group_id": "other"}
                ),
                "meta $group_id is 'other', but the message's $group_id is "
                "'fin'. Nothing sent",
            ),
            (
                lambda: self.company.company_delete(meta={"$group_key": "team_id"}),
                "meta $group_key is 'team_id', but the message's $group_key is "
                "'$company_id'. Nothing sent",
            ),
            (
                lambda: self.mp.people_set(
                    combined, {"plan": "pro"}, meta={"$token": "other"}
                ),
                "meta $token is 'other', but this client's token differs. Nothing sent",
            ),
            (
                lambda: self.mp.group_update(
                    {
                        "$token": "other",
                        "$group_key": "dept",
                        "$group_id": "fin",
                        "$company_id": COMPANY_ID,
                        "$set": {},
                    }
                ),
                "message $token is 'other', but this client's token differs. "
                "Nothing sent",
            ),
            (
                lambda: self.mp.people_set(
                    identity,
                    {"plan": "pro"},
                    meta={"$distinct_id": "$company:other|$user:u2"},
                ),
                "meta $distinct_id is '$company:other|$user:u2', but an "
                "identity names the profile. Pass either an identity or a "
                "$distinct_id, not both. Nothing sent",
            ),
            (
                lambda: self.mp.people_set(
                    self.user, {"plan": "pro"}, meta={"$distinct_id": "u2"}
                ),
                "meta $distinct_id is 'u2', but an identity names the profile. "
                "Pass either an identity or a $distinct_id, not both. Nothing sent",
            ),
        ):
            with pytest.raises(ValueError, match="Nothing sent") as error:
                send()
            assert str(error.value) == message

        self.assert_nothing_sent()

    def test_meta_that_repeats_an_update_is_sent(self):
        meta = {
            "$token": TOKEN,
            "$group_key": "$user_id",
            "$group_id": USER_ID,
            "$ip": "1.2.3.4",
            "$ignore_time": True,
            "$time": 5,
        }

        self.mp.people_set(self.user, {"plan": "pro"}, meta=meta)

        expected = user_update("$set", {"plan": "pro"})
        expected.update({"$ip": "1.2.3.4", "$ignore_time": True, "$time": 5})
        self.assert_only_groups_update(expected)

    def test_meta_that_repeats_an_integer_id_keeps_the_string_id(self):
        user = MixpanelIdentity(user_id=42, company_id=COMPANY_ID)

        self.mp.people_set(user, {"plan": "pro"}, meta={"$group_id": 42})

        _, message = self.only_sent()
        assert message["$group_id"] == "42"
        assert message["$company_id"] == COMPANY_ID

    def test_meta_that_repeats_a_group_update_is_sent(self):
        self.company.group_set(
            "team_id",
            TEAM_ID,
            {"name": "Core"},
            meta={"$group_id": TEAM_ID, "$token": TOKEN, "$ip": "1.2.3.4"},
        )

        expected = team_update("$set", {"name": "Core"})
        expected["$ip"] = "1.2.3.4"
        self.assert_only_groups_update(expected)

    def test_meta_that_repeats_an_identity_distinct_id_is_sent(self):
        identity = MixpanelIdentity(
            distinct_id=COMBINED_DISTINCT_ID, user_id=USER_ID, company_id=COMPANY_ID
        )

        self.mp.people_set(
            identity, {"plan": "pro"}, meta={"$distinct_id": COMBINED_DISTINCT_ID}
        )

        self.assert_only_groups_update(user_update("$set", {"plan": "pro"}))

    def test_meta_retargets_without_hierarchical_groups(self):
        mp = make_client(self.consumer, hierarchical_groups=False)

        mp.group_set("dept", "fin", {"x": 1}, meta={"$group_id": "other"})

        assert self.only_sent() == (
            "groups",
            {
                "$token": TOKEN,
                "$time": NOW,
                "$group_key": "dept",
                "$group_id": "other",
                "$set": {"x": 1},
            },
        )


class TestConsumer:
    @classmethod
    def setup_class(cls):
        cls.consumer = mixpanel.Consumer(request_timeout=30)

    def test_send_events(self):
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/track",
                json={"status": 1, "error": None},
                status=200,
                match=[
                    urlencoded_params_matcher(
                        {"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'}
                    )
                ],
            )
            self.consumer.send("events", '{"foo":"bar"}')

    def test_send_people(self):
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/engage",
                json={"status": 1, "error": None},
                status=200,
                match=[
                    urlencoded_params_matcher(
                        {"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'}
                    )
                ],
            )
            self.consumer.send("people", '{"foo":"bar"}')

    def test_server_success(self):
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/track",
                json={"status": 1, "error": None},
                status=200,
                match=[
                    urlencoded_params_matcher(
                        {"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'}
                    )
                ],
            )
            self.consumer.send("events", '{"foo":"bar"}')

    def test_server_invalid_data(self):
        with responses.RequestsMock() as rsps:
            error_msg = "bad data"
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/track",
                json={"status": 0, "error": error_msg},
                status=200,
                match=[
                    urlencoded_params_matcher(
                        {"ip": "0", "verbose": "1", "data": '{INVALID "foo":"bar"}'}
                    )
                ],
            )

            with pytest.raises(mixpanel.MixpanelException) as exc:
                self.consumer.send("events", '{INVALID "foo":"bar"}')
            assert error_msg in str(exc)

    def test_server_unauthorized(self):
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/track",
                json={"status": 0, "error": "unauthed"},
                status=401,
                match=[
                    urlencoded_params_matcher(
                        {"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'}
                    )
                ],
            )
            with pytest.raises(mixpanel.MixpanelException) as exc:
                self.consumer.send("events", '{"foo":"bar"}')
            assert "unauthed" in str(exc)

    def test_server_forbidden(self):
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/track",
                json={"status": 0, "error": "forbade"},
                status=403,
                match=[
                    urlencoded_params_matcher(
                        {"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'}
                    )
                ],
            )
            with pytest.raises(mixpanel.MixpanelException) as exc:
                self.consumer.send("events", '{"foo":"bar"}')
            assert "forbade" in str(exc)

    def test_server_5xx(self):
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/track",
                body="Internal server error",
                status=500,
                match=[
                    urlencoded_params_matcher(
                        {"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'}
                    )
                ],
            )
            with pytest.raises(mixpanel.MixpanelException):
                self.consumer.send("events", '{"foo":"bar"}')

    def test_consumer_override_api_host(self):
        consumer = mixpanel.Consumer(api_host="api-zoltan.mixpanel.com")

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api-zoltan.mixpanel.com/track",
                json={"status": 1, "error": None},
                status=200,
                match=[
                    urlencoded_params_matcher(
                        {"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'}
                    )
                ],
            )
            consumer.send("events", '{"foo":"bar"}')

        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api-zoltan.mixpanel.com/engage",
                json={"status": 1, "error": None},
                status=200,
                match=[
                    urlencoded_params_matcher(
                        {"ip": "0", "verbose": "1", "data": '{"foo":"bar"}'}
                    )
                ],
            )
            consumer.send("people", '{"foo":"bar"}')

    def test_unknown_endpoint(self):
        with pytest.raises(mixpanel.MixpanelException):
            self.consumer.send("unknown", "1")


class TestBufferedConsumer:
    @classmethod
    def setup_class(cls):
        cls.MAX_LENGTH = 10
        cls.consumer = mixpanel.BufferedConsumer(cls.MAX_LENGTH)
        cls.consumer._consumer = LogConsumer()
        cls.log = cls.consumer._consumer.log

    def setup_method(self):
        del self.log[:]

    def test_buffer_hold_and_flush(self):
        self.consumer.send("events", '"Event"')
        assert len(self.log) == 0
        self.consumer.flush()
        assert self.log == [("events", ["Event"])]

    def test_buffer_fills_up(self):
        for _i in range(self.MAX_LENGTH - 1):
            self.consumer.send("events", '"Event"')
        assert len(self.log) == 0

        self.consumer.send("events", '"Last Event"')
        assert len(self.log) == 1
        assert self.log == [
            (
                "events",
                [
                    "Event",
                    "Event",
                    "Event",
                    "Event",
                    "Event",
                    "Event",
                    "Event",
                    "Event",
                    "Event",
                    "Last Event",
                ],
            )
        ]

    def test_unknown_endpoint_raises_on_send(self):
        # Ensure the exception isn't hidden until a flush.
        with pytest.raises(mixpanel.MixpanelException):
            self.consumer.send("unknown", "1")

    def test_useful_reraise_in_flush_endpoint(self):
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/track",
                json={"status": 0, "error": "arbitrary error"},
                status=200,
            )

            broken_json = "{broken JSON"
            consumer = mixpanel.BufferedConsumer(2)
            consumer.send("events", broken_json)

            with pytest.raises(mixpanel.MixpanelException) as excinfo:
                consumer.flush()
            assert excinfo.value.message == f"[{broken_json}]"
            assert excinfo.value.endpoint == "events"

    def test_send_remembers_api_key(self):
        self.consumer.send("imports", '"Event"', api_key="MY_API_KEY")
        assert len(self.log) == 0
        self.consumer.flush()
        assert self.log == [("imports", ["Event"], ("MY_API_KEY", None))]

    def test_send_remembers_api_secret(self):
        self.consumer.send("imports", '"Event"', (None, "ZZZZZZ"))
        assert len(self.log) == 0
        self.consumer.flush()
        assert self.log == [("imports", ["Event"], (None, "ZZZZZZ"))]


class TestFunctional:
    @classmethod
    def setup_class(cls):
        cls.TOKEN = "12345"
        cls.mp = mixpanel.Mixpanel(cls.TOKEN)
        cls.mp._now = lambda: 1000

    def test_track_functional(self):
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/track",
                json={"status": 1, "error": None},
                status=200,
            )

            self.mp.track(
                "player1",
                "button_press",
                {"size": "big", "color": "blue", "$insert_id": "xyz1200"},
            )

            body = rsps.calls[0].request.body
            wrapper = dict(urllib_parse.parse_qsl(body))
            data = json.loads(wrapper["data"])
            del wrapper["data"]

            assert wrapper == {"ip": "0", "verbose": "1"}
            expected_data = {
                "event": "button_press",
                "properties": {
                    "size": "big",
                    "color": "blue",
                    "mp_lib": "python",
                    "token": "12345",
                    "distinct_id": "player1",
                    "$lib_version": mixpanel.__version__,
                    "time": 1000,
                    "$insert_id": "xyz1200",
                },
            }
            assert expected_data == data

    def test_people_set_functional(self):
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.POST,
                "https://api.mixpanel.com/engage",
                json={"status": 1, "error": None},
                status=200,
            )

            self.mp.people_set(
                "amq", {"birth month": "october", "favorite color": "purple"}
            )
            body = rsps.calls[0].request.body
            wrapper = dict(urllib_parse.parse_qsl(body))
            data = json.loads(wrapper["data"])
            del wrapper["data"]

            assert wrapper == {"ip": "0", "verbose": "1"}
            expected_data = {
                "$distinct_id": "amq",
                "$set": {"birth month": "october", "favorite color": "purple"},
                "$time": 1000,
                "$token": "12345",
            }
            assert expected_data == data


class TestServiceAccountAuth:
    """Test service account authentication."""

    TOKEN = "test-token"
    SERVICE_ACCOUNT_USERNAME = "test-user"
    SERVICE_ACCOUNT_SECRET = "test-secret"
    PROJECT_ID = "123456"
    API_SECRET = "test-api-secret"
    DISTINCT_ID = "test-user-123"

    def _verify_basic_auth(self, username, secret):
        """Helper to verify Basic Auth header."""
        expected_auth = base64.b64encode(f"{username}:{secret}".encode()).decode()
        return f"Basic {expected_auth}"

    @responses.activate
    def test_consumer_with_service_account(self):
        """Test Consumer uses service account for Basic Auth when passed to /import endpoint."""
        responses.add(
            responses.POST,
            "https://api.mixpanel.com/import",
            json={"status": 1, "error": None},
        )

        credentials = mixpanel.ServiceAccountCredentials(
            username=self.SERVICE_ACCOUNT_USERNAME,
            secret=self.SERVICE_ACCOUNT_SECRET,
            project_id=self.PROJECT_ID,
        )
        consumer = mixpanel.Consumer(credentials=credentials)

        event = json.dumps({"event": "test_event", "properties": {"token": self.TOKEN}})
        consumer.send("imports", event)

        assert len(responses.calls) == 1
        request = responses.calls[0].request

        # Verify Basic Auth header
        auth_header = request.headers.get("Authorization")
        expected_auth = self._verify_basic_auth(
            self.SERVICE_ACCOUNT_USERNAME,
            self.SERVICE_ACCOUNT_SECRET,
        )
        assert auth_header == expected_auth

        # Verify project_id query parameter is present (required for service account auth)
        assert "project_id=" + self.PROJECT_ID in request.url

    @responses.activate
    def test_mixpanel_with_service_account(self):
        """Test that track() does NOT use service account credentials.

        Service account credentials are only for /import and feature flag endpoints,
        not for regular tracking endpoints like /track, /engage, or /groups.
        """
        responses.add(
            responses.POST,
            "https://api.mixpanel.com/track",
            json={"status": 1, "error": None},
        )

        credentials = mixpanel.ServiceAccountCredentials(
            username=self.SERVICE_ACCOUNT_USERNAME,
            secret=self.SERVICE_ACCOUNT_SECRET,
            project_id=self.PROJECT_ID,
        )
        mp = mixpanel.Mixpanel(self.TOKEN, credentials=credentials)

        mp.track("test_user", "test_event")

        assert len(responses.calls) == 1
        request = responses.calls[0].request

        # Verify NO auth header for track() - credentials only used for /import
        auth_header = request.headers.get("Authorization")
        assert auth_header is None

        # Verify NO project_id query param for track()
        assert "project_id" not in request.url

    @responses.activate
    def test_service_account_takes_precedence_over_api_secret(self):
        """Test service account credentials take precedence over api_secret."""
        responses.add(
            responses.POST,
            "https://api.mixpanel.com/import",
            json={"status": 1, "error": None},
        )

        credentials = mixpanel.ServiceAccountCredentials(
            username=self.SERVICE_ACCOUNT_USERNAME,
            secret=self.SERVICE_ACCOUNT_SECRET,
            project_id=self.PROJECT_ID,
        )
        mp = mixpanel.Mixpanel(self.TOKEN, credentials=credentials)

        # import_data provides api_secret, but service account should take precedence
        mp.import_data(
            api_key="old_api_key",
            distinct_id="test_user",
            event_name="test_event",
            timestamp=1000,
            api_secret="different_secret",
        )

        assert len(responses.calls) == 1
        request = responses.calls[0].request

        # Verify service account credentials are used, not api_secret
        auth_header = request.headers.get("Authorization")
        expected_auth = self._verify_basic_auth(
            self.SERVICE_ACCOUNT_USERNAME,
            self.SERVICE_ACCOUNT_SECRET,
        )
        assert auth_header == expected_auth

    @responses.activate
    def test_fallback_to_api_secret_when_no_service_account(self):
        """Test fallback to api_secret when no service account is configured."""
        responses.add(
            responses.POST,
            "https://api.mixpanel.com/import",
            json={"status": 1, "error": None},
        )

        mp = mixpanel.Mixpanel(self.TOKEN)

        api_secret = "test_api_secret"
        mp.import_data(
            api_key="old_api_key",
            distinct_id="test_user",
            event_name="test_event",
            timestamp=1000,
            api_secret=api_secret,
        )

        assert len(responses.calls) == 1
        request = responses.calls[0].request

        # Verify api_secret is used
        auth_header = request.headers.get("Authorization")
        expected_auth = self._verify_basic_auth(api_secret, "")
        assert auth_header == expected_auth

    @responses.activate
    def test_buffered_consumer_with_service_account(self):
        """Test BufferedConsumer does NOT send credentials for track().

        Service account credentials are only for /import and feature flag endpoints.
        Even when configured on the Mixpanel instance, they should not be used for /track.
        """
        responses.add(
            responses.POST,
            "https://api.mixpanel.com/track",
            json={"status": 1, "error": None},
        )

        credentials = mixpanel.ServiceAccountCredentials(
            username=self.SERVICE_ACCOUNT_USERNAME,
            secret=self.SERVICE_ACCOUNT_SECRET,
            project_id=self.PROJECT_ID,
        )

        # Pass credentials to BufferedConsumer - they should NOT be used for /track
        consumer = mixpanel.BufferedConsumer(max_size=1, credentials=credentials)
        mp = mixpanel.Mixpanel(self.TOKEN, consumer=consumer)

        mp.track(self.DISTINCT_ID, "test_event")

        assert len(responses.calls) == 1
        request = responses.calls[0].request

        # Verify NO auth header for /track - credentials only used for /import
        auth_header = request.headers.get("Authorization")
        assert auth_header is None

        # Verify NO project_id query param
        assert "project_id" not in request.url

    @responses.activate
    def test_no_auth_header_without_credentials(self):
        """Test no auth header is sent when no credentials are provided."""
        responses.add(
            responses.POST,
            "https://api.mixpanel.com/track",
            json={"status": 1, "error": None},
        )

        consumer = mixpanel.Consumer()
        event = json.dumps({"event": "test_event", "properties": {"token": self.TOKEN}})
        consumer.send("events", event)

        assert len(responses.calls) == 1
        request = responses.calls[0].request

        # Verify no Authorization header
        assert "Authorization" not in request.headers

    def test_credentials_require_all_fields(self):
        """Test ServiceAccountCredentials validates all required fields are provided."""
        # Empty username
        with pytest.raises(ValueError, match="username cannot be empty"):
            mixpanel.ServiceAccountCredentials(
                username="", secret="secret", project_id="123"
            )

        # Empty secret
        with pytest.raises(ValueError, match="secret cannot be empty"):
            mixpanel.ServiceAccountCredentials(
                username="user", secret="", project_id="123"
            )

        # Empty project_id
        with pytest.raises(ValueError, match="project_id cannot be empty"):
            mixpanel.ServiceAccountCredentials(
                username="user", secret="secret", project_id=""
            )

        # Whitespace-only username
        with pytest.raises(ValueError, match="username cannot be empty"):
            mixpanel.ServiceAccountCredentials(
                username="   ", secret="secret", project_id="123"
            )

        # Whitespace-only secret
        with pytest.raises(ValueError, match="secret cannot be empty"):
            mixpanel.ServiceAccountCredentials(
                username="user", secret="   ", project_id="123"
            )

        # Whitespace-only project_id
        with pytest.raises(ValueError, match="project_id cannot be empty"):
            mixpanel.ServiceAccountCredentials(
                username="user", secret="secret", project_id="   "
            )

    def test_credentials_rejects_non_string_types(self):
        """Test ServiceAccountCredentials rejects non-string types with clear error messages."""
        # Integer project_id (common mistake when copying from dashboard)
        with pytest.raises(TypeError, match="project_id must be a string"):
            mixpanel.ServiceAccountCredentials(
                username="user", secret="secret", project_id=123456
            )

        # Integer username
        with pytest.raises(TypeError, match="username must be a string"):
            mixpanel.ServiceAccountCredentials(
                username=12345, secret="secret", project_id="123"
            )

        # Integer secret
        with pytest.raises(TypeError, match="secret must be a string"):
            mixpanel.ServiceAccountCredentials(
                username="user", secret=12345, project_id="123"
            )

        # None values
        with pytest.raises(TypeError, match="username must be a string"):
            mixpanel.ServiceAccountCredentials(
                username=None, secret="secret", project_id="123"
            )

        with pytest.raises(TypeError, match="secret must be a string"):
            mixpanel.ServiceAccountCredentials(
                username="user", secret=None, project_id="123"
            )

        with pytest.raises(TypeError, match="project_id must be a string"):
            mixpanel.ServiceAccountCredentials(
                username="user", secret="secret", project_id=None
            )

    def test_credentials_strips_whitespace(self):
        """Test ServiceAccountCredentials strips leading/trailing whitespace."""
        credentials = mixpanel.ServiceAccountCredentials(
            username="  test-user  ", secret="  test-secret  ", project_id="  123456  "
        )

        assert credentials.username == "test-user"
        assert credentials.secret == "test-secret"
        assert credentials.project_id == "123456"

    def test_credentials_repr_hides_secret(self):
        """Test ServiceAccountCredentials __repr__ doesn't expose the secret."""
        credentials = mixpanel.ServiceAccountCredentials(
            username="test-user", secret="test-secret", project_id="123456"
        )
        repr_str = repr(credentials)

        assert "test-user" in repr_str
        assert "test-secret" not in repr_str
        assert "***" in repr_str
        assert "123456" in repr_str

    @responses.activate
    def test_buffered_consumer_import_with_service_account(self):
        """Test BufferedConsumer DOES send credentials for import_data().

        Service account credentials should be used for /import endpoint,
        even when using BufferedConsumer.
        """
        responses.add(
            responses.POST,
            "https://api.mixpanel.com/import",
            json={"status": 1, "error": None},
        )

        credentials = mixpanel.ServiceAccountCredentials(
            username=self.SERVICE_ACCOUNT_USERNAME,
            secret=self.SERVICE_ACCOUNT_SECRET,
            project_id=self.PROJECT_ID,
        )

        consumer = mixpanel.BufferedConsumer(max_size=1, credentials=credentials)
        mp = mixpanel.Mixpanel(self.TOKEN, consumer=consumer)

        mp.import_data(
            api_key=None,
            distinct_id=self.DISTINCT_ID,
            event_name="test_event",
            timestamp=1000,
        )

        assert len(responses.calls) == 1
        request = responses.calls[0].request

        # Verify Basic Auth header IS present for /import
        auth_header = request.headers.get("Authorization")
        expected_auth = self._verify_basic_auth(
            self.SERVICE_ACCOUNT_USERNAME,
            self.SERVICE_ACCOUNT_SECRET,
        )
        assert auth_header == expected_auth

        # Verify project_id query param IS present for /import
        assert f"project_id={self.PROJECT_ID}" in request.url

    def test_warns_when_credentials_ignored(self):
        """Test that a warning is logged when credentials are passed to Mixpanel with a custom consumer."""
        credentials = mixpanel.ServiceAccountCredentials(
            username=self.SERVICE_ACCOUNT_USERNAME,
            secret=self.SERVICE_ACCOUNT_SECRET,
            project_id=self.PROJECT_ID,
        )

        consumer = mixpanel.BufferedConsumer(max_size=1)

        # Should warn when both consumer and credentials are provided
        with patch("mixpanel.logger.warning") as mock_warning:
            mixpanel.Mixpanel(self.TOKEN, consumer=consumer, credentials=credentials)
            mock_warning.assert_called_once()
            assert (
                "ignored when a custom consumer is provided"
                in mock_warning.call_args[0][0]
            )

        # Should NOT warn when only credentials are provided (consumer is auto-created)
        with patch("mixpanel.logger.warning") as mock_warning:
            mixpanel.Mixpanel(self.TOKEN, credentials=credentials)
            mock_warning.assert_not_called()

        # Should NOT warn when only consumer is provided (no credentials)
        with patch("mixpanel.logger.warning") as mock_warning:
            mixpanel.Mixpanel(self.TOKEN, consumer=consumer)
            mock_warning.assert_not_called()
