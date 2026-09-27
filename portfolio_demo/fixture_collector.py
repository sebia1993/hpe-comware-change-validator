"""Synthetic CLI collection only; comparisons remain production engine work."""

import json
from pathlib import Path
from core.models import CommandResult, CommandSpec, Device
from core.workflow import BB3_OFF_STAGE, CUSTOM_STAGE

DATA = json.loads((Path(__file__).parent / "demo_data/snapshots.json").read_text())
DEVICES = [Device("DEMO-BB3", "192.0.2.3"), Device("DEMO-BB4", "192.0.2.4")]
COMMANDS = [
    CommandSpec(id=k, command=v[0], category=v[1]) for k, v in DATA["commands"].items()
]


def collect(stage, *, vlan=False, resource=False, timeout=False):
    batches = {}
    for device in DEVICES:
        results = []
        for spec in COMMANDS:
            output = DATA["commands"][spec.id][2]
            if stage == BB3_OFF_STAGE:
                if device.name == "DEMO-BB3":
                    output = None
                elif spec.id in (
                    "interface_brief",
                    "link_aggregation_summary",
                    "ospf_peer",
                ):
                    output = DATA["scenarios"]["critical"][spec.id]
                elif spec.id == "vrrp_status":
                    output = DATA["scenarios"]["unexpected"][spec.id]
            if stage == CUSTOM_STAGE:
                if vlan:
                    output = DATA["scenarios"]["expected"].get(spec.id, output)
                if resource and spec.id == "cpu_usage":
                    output = DATA["scenarios"]["critical"][spec.id]
                if timeout and device.name == "DEMO-BB3" and spec.id == "ospf_peer":
                    output = None
            result = CommandResult.started(device, spec)
            result.success = output is not None
            result.output = output or ""
            result.error_message = (
                "" if result.success else "Synthetic collection timeout"
            )
            results.append(result.finish())
        batches[device.name] = results
    return batches
