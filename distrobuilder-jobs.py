#!/usr/bin/env python3
"""Durable, non-blocking jobs for MOS Distrobuilder.

The command frontend launches this small supervisor in a separate session.
It writes status to persistent storage and never requires the browser to
remain connected. Worker execution and status changes are serialized.
"""
import base64
import binascii
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

PLUGIN = Path("/boot/optional/plugins/distrobuilder")
SETTINGS = PLUGIN / "settings.json"
PROVISIONER = "/usr/bin/plugins/distrobuilder-provision"
SCRIPT = "/usr/bin/plugins/distrobuilder-jobs"
JOB_RE = re.compile(r"^[0-9a-f]{32}$")


def storage():
    conf = json.loads(SETTINGS.read_text()) if SETTINGS.is_file() else {}
    directory = conf.get("log_dir")
    if not isinstance(directory, str) or not directory.startswith("/"):
        raise ValueError("Persistent log folder is not configured")
    path = Path(directory).resolve() / "jobs"
    # MOS's plugin log_dir should be on persistent storage, not the boot USB.
    if not path.parent.is_dir():
        raise ValueError("Configured log directory does not exist")
    path.mkdir(mode=0o750, parents=True, exist_ok=True)
    return path


def atomic_json(path, record):
    fd, temporary = tempfile.mkstemp(prefix=".status-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(record, output, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_job(base, job_id):
    if not JOB_RE.fullmatch(job_id):
        raise ValueError("Invalid job identifier")
    path = base / job_id / "status.json"
    if not path.is_file():
        raise ValueError("Job was not found")
    return json.loads(path.read_text(encoding="utf-8"))


def process_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def visible(base, record):
    result = dict(record)
    if record["state"] in ("running", "queued"):
        pid = record.get("pid")
        worker_missing = (pid is not None and not process_alive(pid))
        launch_failed = (pid is None and time.time() - record.get("created_at", 0) > 30)
        if worker_missing or launch_failed:
            result["state"] = "interrupted"
            result["stage"] = "Worker unavailable; inspect log and any partial artifacts"
            result["finished_at"] = time.time()
            atomic_json(base / record["id"] / "status.json", result)
    logfile = base / record["id"] / "output.log"
    if logfile.is_file():
        with logfile.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - 9000))
            result["log_tail"] = stream.read().decode("utf-8", errors="replace")
    else:
        result["log_tail"] = ""
    if record["kind"] == "build" and record["state"] == "running":
        lines = result["log_tail"]
        if "Creating LXC image" in lines or "compression=xz" in lines:
            result["stage"] = "Compressing root filesystem"
        elif "Update complete" in lines or "Steam Console Client" in lines:
            result["stage"] = "Initializing SteamCMD"
        elif "Setting up " in lines or "Unpacking " in lines:
            result["stage"] = "Installing packages"
    return result


def update(base, job_id, **fields):
    path = base / job_id / "status.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record.update(fields)
    atomic_json(path, record)
    return record


def active_jobs(base):
    for path in base.iterdir():
        if not path.is_dir() or not JOB_RE.fullmatch(path.name):
            continue
        try:
            job = visible(base, read_job(base, path.name))
        except (OSError, ValueError, KeyError):
            continue
        if job.get("state") in ("queued", "running"):
            yield job


def validate_encoding(encoded):
    if not isinstance(encoded, str) or len(encoded) > 16384 or not re.fullmatch(r"[A-Za-z0-9_-]+", encoded):
        raise ValueError("Invalid encoded provisioning payload")
    try:
        return json.loads(base64.b64decode(
            encoded.translate(str.maketrans("-_", "+/")) + "=" * (-len(encoded) % 4),
            validate=True).decode("utf-8"))
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Malformed provisioning payload") from exc


def plan_before_submit(kind, encoded):
    if kind == "provision":
        if not encoded:
            raise ValueError("Missing LXC configuration")
        payload = validate_encoding(encoded)
        if not isinstance(payload, dict) or payload.get("confirm_ip_reserved") is not True:
            raise ValueError("Confirm router reservation before provisioning")
        checked = subprocess.run(["python3", PROVISIONER, "plan", encoded],
                                 capture_output=True, text=True, timeout=25)
        if checked.returncode:
            raise ValueError((checked.stderr or checked.stdout)[-1200:])
        data = json.loads(checked.stdout)
        return data["name"], "Provisioning " + data["name"]
    if kind == "build":
        if encoded:
            raise ValueError("Unexpected build payload")
        conf = json.loads(SETTINGS.read_text())
        template = conf.get("selected_template")
        if not isinstance(template, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+\.ya?ml", template):
            raise ValueError("Select a valid YAML template")
        template_dir = conf.get("template_dir")
        if not isinstance(template_dir, str) or not template_dir.startswith("/"):
            raise ValueError("Template directory is not configured")
        if not (Path(template_dir) / template).is_file():
            raise ValueError("Selected template does not exist")
        return template, "Building " + template
    raise ValueError("Unsupported job type")


def submit(kind, encoded=""):
    base = storage()
    with (base / ".submit.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        target, title = plan_before_submit(kind, encoded)
        for current in active_jobs(base):
            if current["kind"] == "provision" and kind == "provision" and current["target"] == target:
                raise ValueError("An LXC creation job is already running for " + target + ": " + current["id"])
            if current["kind"] == "build" and kind == "build":
                raise ValueError("An image build is already running: " + current["id"])
        job_id = uuid.uuid4().hex
        folder = base / job_id
        folder.mkdir(mode=0o750)
        record = {
            "id": job_id, "kind": kind, "target": target,
            "title": title, "state": "queued", "stage": "Queued",
            "created_at": time.time(), "pid": None,
        }
        atomic_json(folder / "status.json", record)
        request = encoded if kind == "provision" else target
        (folder / "request.txt").write_text(request, encoding="ascii")
        os.chmod(folder / "request.txt", 0o600)
        with (folder / "output.log").open("ab") as logfile:
            worker = subprocess.Popen(
                ["python3", SCRIPT, "worker", job_id],
                stdin=subprocess.DEVNULL, stdout=logfile, stderr=subprocess.STDOUT,
                start_new_session=True, close_fds=True)
        # The worker owns the PID and state transition. Writing its PID
        # here races with a fast-finishing job's final status record.
        return {"accepted": True, "id": job_id, "kind": kind,
                "target": target, "state": "queued"}


def worker(job_id):
    base = storage()
    current = read_job(base, job_id)
    folder = base / job_id
    kind = current["kind"]
    update(base, job_id, state="running", pid=os.getpid(), stage="Starting")
    if kind == "provision":
        encoded = (folder / "request.txt").read_text(encoding="ascii")
        argv = ["python3", PROVISIONER, "create", encoded]
        stage = "Creating and configuring LXC"
    elif kind == "build":
        # The MOS installer stores functions under the installed version,
        # not directly beneath the plugin root.
        available = [path for path in PLUGIN.glob("*/functions")
                     if path.parent.name and all(part.isdigit()
                        for part in path.parent.name.split("."))]
        if not available:
            raise RuntimeError("Installed Distrobuilder functions were not found")
        functions_file = max(available, key=lambda path: tuple(
            int(part) for part in path.parent.name.split(".")))
        recorded = (folder / "request.txt").read_text(encoding="ascii")
        argv = ["bash", "-c",
                'source "$1"; DISTROBUILDER_TEMPLATE_OVERRIDE="$2"; build_selected',
                "_", str(functions_file), recorded]
        stage = "Building image"
    else:
        raise RuntimeError("Unknown job type")
    update(base, job_id, stage=stage)
    try:
        with (folder / "output.log").open("ab", buffering=0) as logfile:
            logfile.write(("Running: " + stage + "\n").encode())
            result = subprocess.run(argv, stdout=logfile, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, timeout=7200)
        if result.returncode:
            update(base, job_id, state="failed", stage="Failed; check job log",
                   exit_code=result.returncode, finished_at=time.time())
            return
        # Exit zero isn't sufficient: check each artifact created by THIS job.
        if kind == "provision":
            config = Path("/var/lib/lxc") / current["target"] / "config"
            if not config.is_file() or "END DISTROBUILDER PROVISIONED" not in config.read_text():
                raise RuntimeError("LXC config missing or not provisioned")
            stage = "LXC created and configuration verified"
        else:
            conf = json.loads(SETTINGS.read_text())
            builds = Path(conf["build_dir"])
            # build_selected writes its exact output path to stdout.
            # Read only the tail: a Distrobuilder apt log can be many MB.
            with (folder / "output.log").open("rb") as stream:
                stream.seek(0, 2)
                stream.seek(max(0, stream.tell() - 16384))
                logfile = stream.read().decode("utf-8", errors="replace")
            match = re.search(r"Build completed: (.+)", logfile)
            if not match:
                raise RuntimeError("No completed image output recorded")
            directory = Path(match.group(1).strip()).resolve()
            if builds.resolve() not in directory.parents:
                raise RuntimeError("Build output outside configured directory")
            expected = ("registry.json", "rootfs.tar.xz", "meta.tar.xz")
            if not all((directory / item).is_file() and (directory / item).stat().st_size > 0
                       for item in expected):
                raise RuntimeError("Build output missing complete image artifacts")
            stage = "Image built and registry artifacts verified"
        update(base, job_id, state="succeeded", stage=stage,
               exit_code=0, finished_at=time.time())
    except Exception as exc:
        print("Job failed:", str(exc), flush=True)
        update(base, job_id, state="failed", stage=str(exc)[-220:],
               finished_at=time.time(), exit_code=1)


def status(job_id):
    base = storage()
    return visible(base, read_job(base, job_id))


def latest():
    base = storage()
    result = []
    for folder in base.iterdir():
        if folder.is_dir() and JOB_RE.fullmatch(folder.name):
            try:
                item = visible(base, read_job(base, folder.name))
                item.pop("log_tail", None)
                result.append(item)
            except (OSError, KeyError, ValueError):
                pass
    result.sort(key=lambda item: item.get("created_at", 0), reverse=True)
    return result[:12]


def main(argv):
    if len(argv) == 2 and argv[1] == "list":
        print(json.dumps(latest()))
    elif len(argv) == 3 and argv[1] == "status":
        print(json.dumps(status(argv[2])))
    elif len(argv) == 3 and argv[1] in ("submit-build", "submit-provision"):
        kind = argv[1].split("-")[1]
        print(json.dumps(submit(kind, argv[2] if kind == "provision" else "")))
    elif len(argv) == 3 and argv[1] == "worker":
        worker(argv[2])
    else:
        raise ValueError("Usage: distrobuilder-jobs list|status ID|submit-build unused|submit-provision PAYLOAD|worker ID")


if __name__ == "__main__":
    try:
        main(sys.argv)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print("Job error:", str(exc), file=sys.stderr)
        sys.exit(1)
