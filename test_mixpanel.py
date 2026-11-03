from __future__ import annotations

import base64
import datetime
import decimal
import json
import re
import time
from unittest.mock import patch
from urllib import parse as urllib_parse

import pytest
import responses
from responses.matchers import urlencoded_params_matcher

import mixpanel


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
            "$company:acme|$user:",  # missing user
            "$company:acme",  # missing user and separator
            "$company:|$user:user_123",  # missing company
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

    def test_combined_distinct_id_splits_at_first_user_separator(self):
        self.hg.people_set("$company:a|b|$user:u|$user:v", {"plan": "pro"})

        message = self.last_message()
        assert message["$company_id"] == "a|b"
        assert message["$group_id"] == "u|$user:v"

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

    def test_people_update_parsed_company_wins(self):
        self.hg.people_update(
            {"$distinct_id": self.COMBINED_ID, "$set": {"plan": "pro"}},
            meta={"$company_id": "other"},
        )

        message = self.last_message()
        assert message["$group_id"] == "user_123"
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

    def test_for_company_rejects_empty(self):
        with pytest.raises(ValueError, match="company_id"):
            self.hg.for_company("")
        with pytest.raises(ValueError, match="company_id"):
            self.hg.for_company(None)

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
