import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "provision-lxc.py"
SPEC = importlib.util.spec_from_file_location("mos_provision", MODULE_PATH)
provision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provision)

IMAGE = {"product": "gameserver", "release": "trixie-wine",
         "arch": "amd64", "variant": "default"}
BASE = {"name": "palworld", "product": "gameserver", "release": "trixie-wine",
        "arch": "amd64", "nic": "eth0", "ip": "192.168.50.96/24",
        "gateway": "192.168.50.1", "dns": "192.168.50.1",
        "game_root": "/mnt/data/gameservers", "mount_binaries": False,
        "tun": False, "autostart": True, "start": False}


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.patches = [
            patch.object(provision, "LXC_ROOT", Path(self.directory.name)),
            patch.object(provision, "interfaces", return_value=[
                {"name": "eth0", "mac": "aa:bb:cc:dd:ee:ff", "up": True}]),
            patch.object(provision, "images", return_value=[IMAGE]),
            patch.object(provision, "checked_dir",
                         side_effect=lambda _path, _label: Path("/mnt/data/gameservers")),
            patch.object(provision, "conflicts", return_value=[]),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_plan_renders_isolated_mount_and_static_ip(self):
        result = provision.plan(BASE)
        self.assertIn("lxc.net.0.ipv4.address = 192.168.50.96/24",
                      result["config_append"])
        self.assertIn("lxc.start.auto = 1", result["config_append"])
        self.assertIn("srv/gameserver none bind,ro", result["config_append"])
        self.assertIn("srv/gameserver/palworld none bind,create=dir",
                      result["config_append"])
        self.assertEqual("192.168.50.1", result["dns"])
        self.assertFalse(result["start"])

    def test_no_existing_name_reuse(self):
        (Path(self.directory.name) / "palworld").mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            provision.plan(BASE)

    def test_wrong_gateway_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Gateway"):
            provision.plan({**BASE, "gateway": "192.168.60.1"})

    def test_ipvlan_parent_is_rejected(self):
        with patch.object(provision, "incompatible_ipvlan_parent", return_value="shim-eth0"):
            with self.assertRaisesRegex(ValueError, "ipvlan"):
                provision.plan(BASE)

    def test_encoded_query_payload_decodes(self):
        import base64
        import json
        import io
        from contextlib import redirect_stdout
        encoded = base64.urlsafe_b64encode(json.dumps(BASE).encode()).decode().rstrip("=")
        output = io.StringIO()
        with redirect_stdout(output):
            provision.main(["provision-lxc.py", "plan", encoded])
        self.assertEqual(json.loads(output.getvalue())["name"], "palworld")

    def test_encoded_query_payload_rejects_punctuation(self):
        with self.assertRaisesRegex(ValueError, "Invalid encoded"):
            provision.main(["provision-lxc.py", "plan", '{"name":"bad"}'])

    def test_invalid_name_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "lowercase"):
            provision.plan({**BASE, "name": "../bad"})

    def test_unknown_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "completed local"):
            provision.plan({**BASE, "release": "unpublished"})

    def test_detected_collision_is_rejected(self):
        with patch.object(provision, "conflicts", return_value=["Docker IPAM lanit"]):
            with self.assertRaisesRegex(ValueError, "Docker IPAM"):
                provision.plan(BASE)


if __name__ == "__main__":
    unittest.main()
