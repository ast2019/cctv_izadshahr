#!/usr/bin/env python3
"""Render Frigate configs and a docker-compose file from the inventory.

Source of truth:
    inventory/instances.yml        — global settings + list of instances
    inventory/cameras/<name>.yml    — camera definitions for each instance

Outputs (all under generated/, which is git-ignored):
    generated/config/<name>/config.yml   — one Frigate config per instance
    generated/compose.generated.yaml     — one compose file for all instances
    generated/instances.tsv              — name/ports table for deploy scripts
    generated/required-env.txt           — every FRIGATE_* var the deploy needs

Adding an instance is purely data-driven: add it to instances.yml and drop a
matching cameras/<name>.yml file — no code changes required.
"""
from __future__ import annotations

import pathlib
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
except ImportError:  # pragma: no cover
    sys.exit("Jinja2 is required: pip install jinja2")

ROOT = pathlib.Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "inventory"
TEMPLATES = ROOT / "templates"
OUTPUT = ROOT / "generated"


def load_yaml(path: pathlib.Path) -> dict:
    if not path.exists():
        sys.exit(f"Inventory file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def build_camera(instance_name: str, cam_name: str, cam: dict, sources: dict) -> dict:
    """Assemble a camera's runtime data, referencing secrets only via env vars.

    A camera points at a named *source* (a credential + host group). All secret
    parts of the URL — host, user, password — become FRIGATE_* env vars derived
    from the source name, so a shared device (e.g. a DVR with many channels) is
    described by a single set of variables.
    """
    source_name = cam.get("source")
    if not source_name:
        sys.exit(f"Camera '{instance_name}/{cam_name}' is missing a 'source'")
    if source_name not in sources:
        sys.exit(
            f"Camera '{instance_name}/{cam_name}' references unknown source "
            f"'{source_name}'"
        )
    source = sources[source_name] or {}

    scheme = cam.get("scheme", source.get("scheme", "rtsp"))
    port = cam.get("rtsp_port", source.get("rtsp_port", 554))
    url_path = cam.get("path", "")

    prefix = f"FRIGATE_{instance_name.upper()}_{source_name.upper()}"
    user_var = f"{prefix}_USER"
    pass_var = f"{prefix}_PASSWORD"
    host_var = f"{prefix}_HOST"

    # Produces e.g. rtsp://{FRIGATE_CAFE_DVR_USER}:{FRIGATE_CAFE_DVR_PASSWORD}@{FRIGATE_CAFE_DVR_HOST}:554/path
    stream_url = "{scheme}://{{{u}}}:{{{p}}}@{{{h}}}:{port}{path}".format(
        scheme=scheme, u=user_var, p=pass_var, h=host_var, port=port, path=url_path
    )

    return {
        "name": cam_name,
        "enabled": bool(cam.get("enabled", True)),
        "stream_url": stream_url,
        "env_vars": [user_var, pass_var, host_var],
    }


def validate_instances(instances: list[dict]) -> None:
    """Fail early on collisions that make deployments hard to scale safely."""
    name_pattern = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
    names: set[str] = set()
    used_ports: dict[int, str] = {}

    for idx, instance in enumerate(instances, start=1):
        name = instance.get("name")
        if not name:
            sys.exit(f"Instance #{idx} is missing required field: name")
        if not isinstance(name, str):
            sys.exit(f"Instance #{idx} has non-string name: {name!r}")
        if not name_pattern.match(name):
            sys.exit(
                f"Instance '{name}' has invalid name. Use lowercase letters, digits, '_' or '-'."
            )
        if name in names:
            sys.exit(f"Duplicate instance name: '{name}'")
        names.add(name)

        for port_key in ("ui_port", "rtsp_port", "webrtc_port"):
            if port_key not in instance:
                sys.exit(f"Instance '{name}' is missing required field: {port_key}")
            port = instance[port_key]
            if not isinstance(port, int):
                sys.exit(
                    f"Instance '{name}' field '{port_key}' must be an integer, got {port!r}"
                )
            owner = used_ports.get(port)
            if owner is not None:
                sys.exit(
                    f"Port collision: instance '{name}' {port_key}={port} already used by {owner}"
                )
            used_ports[port] = f"instance '{name}'"


def main() -> int:
    inventory = load_yaml(INVENTORY / "instances.yml")
    settings = inventory.get("global", {})
    instances = inventory.get("instances", [])
    if not instances:
        sys.exit("No instances defined in inventory/instances.yml")
    validate_instances(instances)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    config_tpl = env.get_template("frigate-config.yml.j2")
    service_tpl = env.get_template("compose.instance.yml.j2")

    (OUTPUT / "config").mkdir(parents=True, exist_ok=True)

    services: list[str] = []
    tsv_rows: list[str] = []
    required_env: list[str] = []

    for instance in instances:
        name = instance["name"]
        cameras_doc = load_yaml(INVENTORY / "cameras" / f"{name}.yml")
        sources = cameras_doc.get("sources", {}) or {}
        cameras_raw = cameras_doc.get("cameras", {}) or {}
        if not cameras_raw:
            sys.exit(f"No cameras defined for instance '{name}'")

        cameras = []
        for cam_name, cam in cameras_raw.items():
            camera = build_camera(name, cam_name, cam or {}, sources)
            cameras.append(camera)
            required_env.extend(camera["env_vars"])

        config_yaml = config_tpl.render(instance=instance, g=settings, cameras=cameras)
        instance_dir = OUTPUT / "config" / name
        instance_dir.mkdir(parents=True, exist_ok=True)
        (instance_dir / "config.yml").write_text(config_yaml, encoding="utf-8")

        services.append(service_tpl.render(instance=instance, g=settings))
        tsv_rows.append(
            f"{name}\t{instance['ui_port']}\t{instance['rtsp_port']}\t{instance['webrtc_port']}"
        )

    compose = (
        "# Managed by GitOps — DO NOT EDIT BY HAND\n"
        "# Rendered from inventory/ by scripts/render.py\n"
        "name: frigate\n\n"
        "services:\n" + "\n".join(services) + "\n"
    )
    (OUTPUT / "compose.generated.yaml").write_text(compose, encoding="utf-8")
    (OUTPUT / "instances.tsv").write_text("\n".join(tsv_rows) + "\n", encoding="utf-8")

    # Deduplicate env vars while preserving first-seen order.
    seen: set[str] = set()
    unique_env = [v for v in required_env if not (v in seen or seen.add(v))]
    (OUTPUT / "required-env.txt").write_text("\n".join(unique_env) + "\n", encoding="utf-8")

    names = ", ".join(i["name"] for i in instances)
    print(f"Rendered {len(instances)} instance(s): {names}")
    print(f"Output written to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
