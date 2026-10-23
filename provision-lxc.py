#!/usr/bin/env python3
"""MOS LXC provisioner: strict dry-run plans, then guarded create."""
import base64
import binascii
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile

SETTINGS = Path("/boot/optional/plugins/distrobuilder/settings.json")
LXC_ROOT = Path("/var/lib/lxc")
REGISTRY = "lxc-registry.time-wall.ts.net"
IDENT = re.compile(r"^[a-z][a-z0-9-]{0,39}$")


def run(args, timeout=12):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=timeout).stdout


def settings():
    return json.loads(SETTINGS.read_text()) if SETTINGS.is_file() else {}


def interfaces():
    try:
        records = json.loads(run(["ip", "-j", "link", "show"]))
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    return [
        {"name": x["ifname"], "mac": x.get("address", ""), "up": "UP" in x.get("flags", [])}
        for x in records if x.get("ifname")
        and Path("/sys/class/net", x["ifname"], "device").exists()
    ]


def incompatible_ipvlan_parent(nic):
    """macvlan and ipvlan on one parent cannot be mixed reliably."""
    try:
        links = json.loads(run(["ip", "-d", "-j", "link", "show"]))
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    parent = next((x for x in links if x.get("ifname") == nic), None)
    if parent is None:
        return None
    for child in links:
        if child.get("link_index") == parent.get("ifindex") and \
           (child.get("linkinfo") or {}).get("info_kind") == "ipvlan":
            return child.get("ifname") or "unknown ipvlan child"
    return None


def images():
    base = Path(settings().get("build_dir") or "/mnt/user/@storage/distrobuilder/builds")
    discovered = {}
    if base.is_dir():
        for folder in base.iterdir():
            if not folder.is_dir() or folder.is_symlink():
                continue
            if not all((folder / filename).is_file()
                       for filename in ("registry.json", "rootfs.tar.xz", "meta.tar.xz")):
                continue
            try:
                item = json.loads((folder / "registry.json").read_text())
                key = (item["product"], item["release"], item["arch"], item["variant"])
                if all(isinstance(part, str) and part for part in key):
                    discovered[key] = dict(zip(("product", "release", "arch", "variant"), key))
            except (OSError, KeyError, ValueError):
                continue
    return sorted(discovered.values(), key=lambda x: (x["product"], x["release"]))


def local_image_archives(image):
    """Pick the newest complete local build for the selected image.

    A build on apps is not necessarily published by the separate MOS
    SimpleStreams registry. Use LXC's native local template instead.
    """
    base = Path(settings().get("build_dir") or "/mnt/user/@storage/distrobuilder/builds")
    candidates = []
    if base.is_dir():
        for folder in base.iterdir():
            if not folder.is_dir() or folder.is_symlink():
                continue
            registry = folder / "registry.json"
            rootfs = folder / "rootfs.tar.xz"
            metadata = folder / "meta.tar.xz"
            if not all(path.is_file() and path.stat().st_size > 0
                       for path in (registry, rootfs, metadata)):
                continue
            try:
                manifest = json.loads(registry.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if all(manifest.get(key) == value for key, value in image.items()):
                candidates.append((folder.stat().st_mtime, folder.name, metadata, rootfs))
    if not candidates:
        raise ValueError("No complete local archives found for selected image")
    _, _, metadata, rootfs = max(candidates)
    return metadata, rootfs


def defaults():
    return {
        "registry": REGISTRY, "gateway": "192.168.50.1",
        "game_root": "/mnt/user/@gameservers" if Path("/mnt/user/@gameservers").is_dir()
                     else "/mnt/data/gameservers",
        "binary_dir": "/mnt/data/binary-manager/binaries"
                      if Path("/mnt/data/binary-manager/binaries").is_dir()
                      else "/mnt/user/binaries",
    }


def checked_dir(raw, label):
    if not isinstance(raw, str) or not raw.startswith("/") or ".." in Path(raw).parts:
        raise ValueError(label + " must be an absolute directory without '..'")
    path = Path(raw).resolve()
    if path == Path("/") or not path.is_dir():
        raise ValueError(label + " is not an existing directory: " + raw)
    return path


def flag(p, key, default):
    value = p.get(key, default)
    if type(value) is not bool:
        raise ValueError(key + " must be a boolean")
    return value


def conflicts(address):
    """Best-effort local allocation checks. Router reservations need human verification."""
    ip = ipaddress.ip_address(address)
    found = []
    try:
        for item in json.loads(run(["ip", "-j", "-4", "addr", "show"])):
            for assigned in item.get("addr_info", []):
                if assigned.get("local") == address:
                    found.append("host NIC " + item.get("ifname", "?"))
    except (OSError, ValueError, subprocess.SubprocessError):
        found.append("unable to inspect host IPs")
    if LXC_ROOT.is_dir():
        for config in LXC_ROOT.glob("*/config"):
            try:
                text = config.read_text()
            except OSError:
                continue
            for match in re.finditer(r"^\s*lxc\.net\.\d+\.ipv4\.address\s*=\s*(\S+)",
                                     text, re.MULTILINE):
                try:
                    if ipaddress.ip_interface(match.group(1)).ip == ip:
                        found.append("LXC " + config.parent.name)
                except ValueError:
                    pass
    try:
        for neighbor in json.loads(run(["ip", "-j", "neigh", "show"])):
            if neighbor.get("dst") == address and neighbor.get("lladdr") and \
               neighbor.get("state", "").upper() not in ("FAILED", "INCOMPLETE"):
                found.append("neighbor " + neighbor["lladdr"])
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    try:
        ids = run(["docker", "network", "ls", "-q"], timeout=5).splitlines()
        if ids:
            networks = json.loads(run(["docker", "network", "inspect", *ids]))
            for net in networks:
                for entry in (net.get("IPAM") or {}).get("Config") or []:
                    if entry.get("IPRange"):
                        try:
                            if ip in ipaddress.ip_network(entry["IPRange"], strict=False):
                                found.append("Docker IPAM range " + net.get("Name", "?"))
                        except ValueError:
                            pass
                for endpoint in (net.get("Containers") or {}).values():
                    if endpoint.get("IPv4Address", "").split("/")[0] == address:
                        found.append("Docker endpoint " + net.get("Name", "?"))
    except FileNotFoundError:
        pass  # Docker is optional on an LXC-only host.
    except (ValueError, subprocess.SubprocessError):
        found.append("unable to inspect Docker allocations")
    return found


def plan(p):
    if not isinstance(p, dict):
        raise ValueError("Expected a JSON object")
    name = p.get("name", "")
    product, release = p.get("product", "gameserver"), p.get("release", "")
    if not all(isinstance(x, str) and IDENT.fullmatch(x) for x in (name, product, release)):
        raise ValueError("Name, product and release must be lowercase slugs (max 40)")
    if p.get("arch", "amd64") != "amd64":
        raise ValueError("Only amd64 is supported")
    nic = p.get("nic")
    if nic not in [x["name"] for x in interfaces() if x["up"]]:
        raise ValueError("Choose an available UP physical NIC")
    conflicting_link = incompatible_ipvlan_parent(nic)
    if conflicting_link:
        raise ValueError("NIC already has an ipvlan child (" + conflicting_link
                         + "); remove or relocate it before creating macvlan")
    registry = p.get("registry", REGISTRY)
    if not isinstance(registry, str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", registry):
        raise ValueError("Registry must be a DNS hostname without scheme or port")
    try:
        addr = ipaddress.IPv4Interface(p.get("ip", ""))
        gateway = ipaddress.IPv4Address(p.get("gateway", "192.168.50.1"))
        dns = ipaddress.IPv4Address(p.get("dns", str(gateway)))
    except ValueError as exc:
        raise ValueError("Invalid IPv4 CIDR or gateway: " + str(exc)) from exc
    if gateway == addr.ip or gateway not in addr.network:
        raise ValueError("Gateway must belong to subnet and differ from container IP")
    if (LXC_ROOT / name).exists() or (LXC_ROOT / name).is_symlink():
        raise ValueError("Container already exists: " + name)
    image = {"product": product, "release": release, "arch": "amd64", "variant": "default"}
    if image not in images():
        raise ValueError("Image not among completed local registry builds: " + product + "/" + release)
    metadata, rootfs = local_image_archives(image)
    root = checked_dir(p.get("game_root", defaults()["game_root"]), "Game catalogue")
    binary = checked_dir(p.get("binary_dir", defaults()["binary_dir"]), "Binary folder") \
        if flag(p, "mount_binaries", True) else None
    tun = flag(p, "tun", True)
    auto = flag(p, "autostart", True)
    start = flag(p, "start", False)
    if tun and not Path("/dev/net/tun").exists():
        raise ValueError("Host TUN device is missing")
    if (root / name).is_symlink():
        raise ValueError("Game data directory cannot be a symlink")
    collisions = conflicts(str(addr.ip))
    if collisions:
        raise ValueError("IP conflicts/unverified allocations: " + "; ".join(collisions))
    mac_bytes = hashlib.sha256((socket.gethostname() + ":" + name).encode()).digest()[:5]
    mac = "02:" + ":".join(f"{b:02x}" for b in mac_bytes)
    config = [
        "# BEGIN DISTROBUILDER PROVISIONED",
        "lxc.net.0.type = macvlan", f"lxc.net.0.link = {nic}",
        "lxc.net.0.flags = up", "lxc.net.0.name = eth0",
        f"lxc.net.0.hwaddr = {mac}",
        f"lxc.net.0.ipv4.address = {addr}",
        f"lxc.net.0.ipv4.gateway = {gateway}",
        f"lxc.start.auto = {int(auto)}",
        f"lxc.mount.entry = {root} srv/gameserver none bind,create=dir 0 0",
    ]
    if binary:
        config.append(f"lxc.mount.entry = {binary} home/steam/.local/bin none bind,ro,create=dir 0 0")
    if tun:
        config += ["lxc.cgroup2.devices.allow = c 10:200 rwm",
                   "lxc.mount.entry = /dev/net/tun dev/net/tun none bind,create=file 0 0"]
    config.append("# END DISTROBUILDER PROVISIONED")
    return {
        "name": name, "image": image, "nic": nic, "ip": str(addr),
        "gateway": str(gateway), "dns": str(dns), "mac": mac, "game_directory": str(root / name),
        "autostart": auto, "start": start, "config_append": "\n".join(config) + "\n",
        "create_argv": ["lxc-create", "-n", name, "-t", "local", "--",
                        "--metadata", str(metadata), "--fstree", str(rootfs)],
        "warnings": [
            "Reserve the IP in your router; local checks cannot detect every silent device.",
            "A privileged LXC is used to match the existing gameserver image.",
            "The entire shared catalogue is writable by this privileged LXC; protect other games with backups.",
        ],
    }


def create(p):
    if p.get("confirm_ip_reserved") is not True:
        raise ValueError("Confirm IP reservation before creating the LXC")
    import fcntl
    with open("/run/lock/distrobuilder-provision.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = plan(p)
        created = subprocess.run(result["create_argv"], text=True, capture_output=True,
                                 timeout=600)
        if created.returncode:
            raise RuntimeError("lxc-create failed; inspect partial state: " +
                               (created.stderr or created.stdout)[-1500:])
        config = LXC_ROOT / result["name"] / "config"
        if not config.is_file():
            raise RuntimeError("New LXC has no config; inspect partial state")
        original = config.read_text()
        retained = [x for x in original.splitlines()
                    if not re.match(r"\s*lxc\.net\.0\.", x)
                    and not re.match(r"\s*lxc\.start\.auto\s*=", x)]
        updated = "\n".join(retained).rstrip() + "\n\n" + result["config_append"]
        fd, tmp = tempfile.mkstemp(dir=config.parent, prefix=".config-")
        try:
            with os.fdopen(fd, "w") as output:
                output.write(updated)
                output.flush()
                os.fsync(output.fileno())
            os.chmod(tmp, config.stat().st_mode & 0o777)
            os.replace(tmp, config)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        # Seed a resolver before first boot; Tailscale can take ownership
        # only after the guest has network access and authenticates.
        guest_root = LXC_ROOT / result["name"] / "rootfs"
        guest_resolver = guest_root / "etc/resolv.conf"
        if not (guest_root / "etc").is_dir():
            raise RuntimeError("LXC created but expected rootfs/etc is unavailable")
        if guest_resolver.is_symlink():
            guest_resolver.unlink()
        guest_resolver.write_text("# MOS bootstrap DNS; Tailscale may replace after enrollment\n"
                                  + "nameserver " + result["dns"] + "\n")

        data = Path(result["game_directory"])
        if not data.exists():
            data.mkdir(mode=0o755)
            os.chown(data, 1000, 1000)
        if result["start"]:
            started = subprocess.run(["lxc-start", "-n", result["name"]],
                                     capture_output=True, text=True, timeout=90)
            if started.returncode:
                raise RuntimeError("LXC created but startup failed: " + started.stderr[-1000:])
        return {"created": True, "name": result["name"], "started": result["start"],
                "ip": result["ip"], "mac": result["mac"], "config_path": str(config),
                "game_directory": str(data)}


def main(args):
    if len(args) == 2 and args[1] == "info":
        print(json.dumps({"interfaces": interfaces(), "images": images(), "defaults": defaults()}))
        return
    if len(args) != 3 or args[1] not in ("plan", "create"):
        raise ValueError("Usage: provision-lxc.py info | plan JSON | create JSON")
    encoded = args[2]
    if len(encoded) > 16384 or not re.fullmatch(r"[A-Za-z0-9_-]+", encoded):
        raise ValueError("Invalid encoded provisioning payload")
    try:
        decoded = base64.b64decode(encoded.translate(str.maketrans("-_", "+/"))
                                   + "=" * (-len(encoded) % 4), validate=True)
        payload = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise ValueError("Malformed provisioning payload") from exc
    print(json.dumps(plan(payload) if args[1] == "plan" else create(payload)))


if __name__ == "__main__":
    try:
        main(sys.argv)
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print("Provisioning failed: " + str(exc), file=sys.stderr)
        sys.exit(1)
