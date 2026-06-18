"""policy_catalog 단위 테스트.

레포 루트에서 실행:
    python -m unittest tests.install_helper.test_policy_catalog
"""

import json
import unittest

from pydantic import ValidationError

from backend.install_helper.policy_catalog import (
    CHROME_POLICY_KEY,
    ChromePolicyName,
    ExtensionAllowedTypesPolicy,
    ExtensionInstallAllowlistPolicy,
    ExtensionInstallBlocklistPolicy,
    ExtensionInstallForcelistEntry,
    ExtensionInstallForcelistPolicy,
    ExtensionSettingsPolicy,
    ExtensionSettingsRule,
    ExtensionType,
    InstallationMode,
    is_extension_id_or_wildcard,
    is_valid_extension_id,
    render_allowed_types_batch,
    render_allowlist_batch,
    render_blocklist_batch,
    render_extension_settings_batch,
    render_forcelist_batch,
)


VALID_ID_A = "a" * 32
VALID_ID_B = "abcdefghijklmnopabcdefghijklmnop"
INVALID_ID_TOO_SHORT = "abc"
INVALID_ID_WRONG_ALPHABET = "z" * 32


class IdValidationTests(unittest.TestCase):
    def test_valid_id(self):
        self.assertTrue(is_valid_extension_id(VALID_ID_A))
        self.assertTrue(is_valid_extension_id(VALID_ID_B.upper()))

    def test_invalid_id(self):
        self.assertFalse(is_valid_extension_id(INVALID_ID_TOO_SHORT))
        self.assertFalse(is_valid_extension_id(INVALID_ID_WRONG_ALPHABET))
        self.assertFalse(is_valid_extension_id(""))

    def test_wildcard_helper(self):
        self.assertTrue(is_extension_id_or_wildcard("*"))
        self.assertTrue(is_extension_id_or_wildcard(VALID_ID_A))
        self.assertFalse(is_extension_id_or_wildcard("foo"))


class ExtensionSettingsTests(unittest.TestCase):
    def test_force_installed_uses_default_update_url(self):
        rule = ExtensionSettingsRule(installation_mode=InstallationMode.FORCE_INSTALLED)
        self.assertEqual(
            rule.to_dict()["update_url"],
            "https://clients2.google.com/service/update2/crx",
        )

    def test_blocked_mode_omits_update_url(self):
        rule = ExtensionSettingsRule(installation_mode=InstallationMode.BLOCKED)
        self.assertNotIn("update_url", rule.to_dict())

    def test_override_update_url_only_when_true(self):
        rule = ExtensionSettingsRule(
            installation_mode=InstallationMode.NORMAL_INSTALLED,
            override_update_url=True,
        )
        self.assertEqual(rule.to_dict()["override_update_url"], True)
        rule_default = ExtensionSettingsRule(
            installation_mode=InstallationMode.NORMAL_INSTALLED,
        )
        self.assertNotIn("override_update_url", rule_default.to_dict())

    def test_permission_lists_passthrough(self):
        rule = ExtensionSettingsRule(
            installation_mode=InstallationMode.NORMAL_INSTALLED,
            allowed_permissions=["activeTab"],
            blocked_permissions=["downloads"],
            runtime_blocked_hosts=["*://*.example.com"],
        )
        d = rule.to_dict()
        self.assertEqual(d["allowed_permissions"], ["activeTab"])
        self.assertEqual(d["blocked_permissions"], ["downloads"])
        self.assertEqual(d["runtime_blocked_hosts"], ["*://*.example.com"])

    def test_policy_requires_at_least_one_rule(self):
        with self.assertRaises(ValidationError):
            ExtensionSettingsPolicy(rules={})

    def test_policy_rejects_bad_key(self):
        with self.assertRaises(ValidationError):
            ExtensionSettingsPolicy(
                rules={
                    "bogus": ExtensionSettingsRule(
                        installation_mode=InstallationMode.BLOCKED
                    )
                }
            )

    def test_policy_normalizes_uppercase_id(self):
        policy = ExtensionSettingsPolicy(
            rules={
                VALID_ID_A.upper(): ExtensionSettingsRule(
                    installation_mode=InstallationMode.BLOCKED
                )
            }
        )
        self.assertIn(VALID_ID_A, policy.rules)

    def test_policy_json_is_sorted_compact(self):
        policy = ExtensionSettingsPolicy(
            rules={
                "*": ExtensionSettingsRule(installation_mode=InstallationMode.BLOCKED),
                VALID_ID_A: ExtensionSettingsRule(
                    installation_mode=InstallationMode.FORCE_INSTALLED
                ),
            }
        )
        raw = policy.to_json()
        self.assertNotIn(" ", raw)
        parsed = json.loads(raw)
        keys = list(parsed.keys())
        self.assertEqual(keys, sorted(keys))


class ForcelistTests(unittest.TestCase):
    def test_entry_serialization(self):
        entry = ExtensionInstallForcelistEntry(extension_id=VALID_ID_A)
        self.assertEqual(
            entry.to_value(),
            f"{VALID_ID_A};https://clients2.google.com/service/update2/crx",
        )

    def test_entry_rejects_bad_id(self):
        with self.assertRaises(ValidationError):
            ExtensionInstallForcelistEntry(extension_id="bad")

    def test_policy_requires_entries(self):
        with self.assertRaises(ValidationError):
            ExtensionInstallForcelistPolicy(entries=[])


class BlocklistAllowlistTests(unittest.TestCase):
    def test_blocklist_accepts_wildcard(self):
        policy = ExtensionInstallBlocklistPolicy(entries=["*"])
        self.assertEqual(policy.entries, ["*"])

    def test_blocklist_normalizes_case(self):
        policy = ExtensionInstallBlocklistPolicy(entries=[VALID_ID_A.upper()])
        self.assertEqual(policy.entries, [VALID_ID_A])

    def test_allowlist_rejects_wildcard(self):
        with self.assertRaises(ValidationError):
            ExtensionInstallAllowlistPolicy(entries=["*"])


class AllowedTypesTests(unittest.TestCase):
    def test_serialization(self):
        policy = ExtensionAllowedTypesPolicy(
            types=[ExtensionType.EXTENSION, ExtensionType.THEME]
        )
        self.assertEqual(policy.to_list(), ["extension", "theme"])


class BatchRendererTests(unittest.TestCase):
    def _common_assertions(self, script: str, value_name: str):
        self.assertIn("@echo off", script)
        self.assertIn("net session >nul 2>&1", script)
        self.assertIn(CHROME_POLICY_KEY, script)
        self.assertIn(value_name, script)
        self.assertEqual(script.count("\r\n") + 1, len(script.split("\r\n")))

    def test_extension_settings_batch(self):
        policy = ExtensionSettingsPolicy(
            rules={
                VALID_ID_A: ExtensionSettingsRule(
                    installation_mode=InstallationMode.FORCE_INSTALLED
                )
            }
        )
        script = render_extension_settings_batch(policy)
        self._common_assertions(script, ChromePolicyName.EXTENSION_SETTINGS.value)
        self.assertIn("Set-ItemProperty", script)

    def test_forcelist_batch_has_indexed_subkeys(self):
        policy = ExtensionInstallForcelistPolicy(
            entries=[
                ExtensionInstallForcelistEntry(extension_id=VALID_ID_A),
                ExtensionInstallForcelistEntry(extension_id=VALID_ID_B),
            ]
        )
        script = render_forcelist_batch(policy)
        self._common_assertions(
            script, ChromePolicyName.EXTENSION_INSTALL_FORCELIST.value
        )
        self.assertIn("-Name '1'", script)
        self.assertIn("-Name '2'", script)

    def test_blocklist_batch(self):
        policy = ExtensionInstallBlocklistPolicy(entries=["*"])
        script = render_blocklist_batch(policy)
        self._common_assertions(
            script, ChromePolicyName.EXTENSION_INSTALL_BLOCKLIST.value
        )

    def test_allowlist_batch(self):
        policy = ExtensionInstallAllowlistPolicy(entries=[VALID_ID_A])
        script = render_allowlist_batch(policy)
        self._common_assertions(
            script, ChromePolicyName.EXTENSION_INSTALL_ALLOWLIST.value
        )

    def test_allowed_types_batch(self):
        policy = ExtensionAllowedTypesPolicy(types=[ExtensionType.EXTENSION])
        script = render_allowed_types_batch(policy)
        self._common_assertions(
            script, ChromePolicyName.EXTENSION_ALLOWED_TYPES.value
        )

    def test_powershell_escape_single_quote(self):
        rule = ExtensionSettingsRule(
            installation_mode=InstallationMode.NORMAL_INSTALLED,
            runtime_blocked_hosts=["*://it's-broken.example/"],
        )
        policy = ExtensionSettingsPolicy(rules={VALID_ID_A: rule})
        script = render_extension_settings_batch(policy)
        self.assertIn("it''s-broken", script)
        self.assertNotIn("it's-broken", script)


if __name__ == "__main__":
    unittest.main()
