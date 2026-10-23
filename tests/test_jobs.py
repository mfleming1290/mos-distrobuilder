import importlib.util
import json
import sys
from unittest.mock import MagicMock
try:
    import fcntl
except ImportError:
    sys.modules["fcntl"] = MagicMock(LOCK_EX=2)
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "distrobuilder-jobs.py"
SPEC = importlib.util.spec_from_file_location("mos_jobs", MODULE_PATH)
jobs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jobs)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.storage_patch = patch.object(jobs, "storage", return_value=self.base)
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)

    def test_atomic_status_and_log_tail(self):
        folder = self.base / ("a" * 32)
        folder.mkdir()
        record = {"id": folder.name, "kind": "build", "target": "gameserver.yaml",
                  "title": "Build", "state": "succeeded", "stage": "Done",
                  "created_at": time.time(), "pid": 0}
        jobs.atomic_json(folder / "status.json", record)
        (folder / "output.log").write_text("Completed image\n")
        actual = jobs.status(folder.name)
        self.assertEqual("succeeded", actual["state"])
        self.assertIn("Completed image", actual["log_tail"])

    def test_submit_returns_id_without_running_job_in_request(self):
        with patch.object(jobs, "plan_before_submit", return_value=("windrose", "Provisioning windrose")):
            with patch.object(jobs.subprocess, "Popen") as spawned:
                spawned.return_value.pid = 4321
                accepted = jobs.submit("provision", "encoded")
        self.assertTrue(accepted["accepted"])
        self.assertEqual("queued", accepted["state"])
        self.assertRegex(accepted["id"], "^[0-9a-f]{32}$")
        self.assertEqual(1, spawned.call_count)
        record = jobs.read_job(self.base, accepted["id"])
        self.assertEqual("queued", record["state"])
        self.assertEqual("encoded", (self.base / accepted["id"] / "request.txt").read_text())
        self.assertNotIn("encoded", json.dumps(jobs.status(accepted["id"])))

    def test_queued_worker_that_never_starts_is_interrupted(self):
        folder = self.base / ("e" * 32)
        folder.mkdir()
        jobs.atomic_json(folder / "status.json", {
            "id": folder.name, "kind": "provision", "target": "windrose",
            "title": "Provisioning", "state": "queued", "stage": "Queued",
            "created_at": time.time() - 40, "pid": None,
        })
        self.assertEqual("interrupted", jobs.status(folder.name)["state"])

    def test_interrupted_worker_is_visible(self):
        folder = self.base / ("b" * 32)
        folder.mkdir()
        record = {"id": folder.name, "kind": "provision", "target": "windrose",
                  "title": "Provisioning", "state": "running", "stage": "Create",
                  "created_at": time.time(), "pid": 123456789}
        jobs.atomic_json(folder / "status.json", record)
        with patch.object(jobs, "process_alive", return_value=False):
            actual = jobs.status(folder.name)
        self.assertEqual("interrupted", actual["state"])

    def test_submissions_cannot_create_same_lxc_twice(self):
        folder = self.base / ("c" * 32)
        folder.mkdir()
        record = {"id": folder.name, "kind": "provision", "target": "windrose",
                  "title": "Provisioning", "state": "running", "stage": "Create",
                  "created_at": time.time(), "pid": 1}
        jobs.atomic_json(folder / "status.json", record)
        with patch.object(jobs, "plan_before_submit", return_value=("windrose", "Provisioning windrose")):
            with patch.object(jobs, "process_alive", return_value=True):
                with self.assertRaisesRegex(ValueError, "already running"):
                    jobs.submit("provision", "encoded")

    def test_workflow_exposes_no_raw_payload_in_status(self):
        folder = self.base / ("d" * 32)
        folder.mkdir()
        record = {"id": folder.name, "kind": "provision", "target": "windrose",
                  "title": "Provisioning", "state": "succeeded", "stage": "Done",
                  "created_at": time.time(), "pid": 0}
        jobs.atomic_json(folder / "status.json", record)
        self.assertNotIn("request", json.dumps(jobs.status(folder.name)))

    def test_invalid_job_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid job identifier"):
            jobs.status("../unsafe")


if __name__ == "__main__":
    unittest.main()
