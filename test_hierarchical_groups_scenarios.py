"""Hierarchical groups scenarios, one test per scenario.

Each test locks the endpoint, the exact top-level keys of every ``/groups``
message, the operation value, and the identity keys on events.
"""

from __future__ import annotations

import json

import pytest
import responses

import mixpanel
from mixpanel import MixpanelIdentity
from mixpanel.flags.utils import exposure_identity

USER_ID = "my_user_id"
COMPANY_ID = "my_company_id"
TEAM_ID = "my_team_id"
DEVICE_ID = "my_device_id"
COMBINED_DISTINCT_ID = f"$company:{COMPANY_ID}|$user:{USER_ID}"
TOKEN = "12345"
NOW = 1000.1
INSERT_ID = "abcdefg"


class LogConsumer:
    def __init__(self):
        self.log = []

    def send(self, endpoint, json_message, _api_key=None):
        self.log.append((endpoint, json.loads(json_message)))


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


class TestHierarchicalGroupsScenarios:
    def setup_method(self):
        self.consumer = LogConsumer()
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
                    "$device_id": 5,
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
                    "properties": event_properties(**{"$user_id": 42, "$device_id": 5}),
                },
            ),
            (
                "groups",
                {
                    "$token": TOKEN,
                    "$time": NOW,
                    "$group_key": "$company_id",
                    "$group_id": 7,
                    "$company_id": 7,
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
