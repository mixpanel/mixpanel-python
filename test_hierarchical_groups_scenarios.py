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

    def test_set_company_property_without_for_company(self):
        self.mp.group_set("$company_id", COMPANY_ID, {"tier": "enterprise"})

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

    # Unsupported / rejected

    def test_identify_without_company(self):
        identity = MixpanelIdentity(user_id=USER_ID)

        with pytest.raises(ValueError, match="needs a company"):
            self.mp.people_set(identity, {"plan": "pro"})
        with pytest.raises(ValueError, match="needs a company"):
            self.mp.track(identity, "Signup")

        self.assert_nothing_sent()

    def test_set_user_property_without_user(self):
        with pytest.raises(ValueError, match="require a user id"):
            self.mp.people_set(MixpanelIdentity(company_id=COMPANY_ID), {"plan": "pro"})

        self.assert_nothing_sent()

    def test_set_company_property_for_another_company(self):
        with pytest.raises(ValueError, match="its own id"):
            self.mp.for_company("other_company").group_set(
                "$company_id", COMPANY_ID, {"tier": "enterprise"}
            )

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
