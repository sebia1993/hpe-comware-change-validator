"""Synthetic CLI collection only; comparisons remain production engine work."""

import json
from pathlib import Path

from core.models import CommandResult, CommandSpec, Device
from core.workflow import BB3_OFF_STAGE, CUSTOM_STAGE

DATA = json.loads((Path(__file__).parent / "demo_data/snapshots.json").read_text())
DEVICES = [Device("DEMO-BB3", "192.0.2.3"), Device("DEMO-BB4", "192.0.2.4")]
COMMANDS = [
    CommandSpec(id=key, command=value[0], category=value[1])
    for key, value in DATA["commands"].items()
]


def baseline_output(device_name, command_id):
    return DATA["device_baselines"].get(device_name, {}).get(
        command_id,
        DATA["commands"][command_id][2],
    )


def scenario_output(scenario, device_name, command_id, default):
    payload = DATA["scenarios"].get(scenario, {})
    device_payload = payload.get(device_name, {})
    if command_id not in device_payload:
        return default
    return device_payload[command_id]


def collect(
    stage,
    *,
    vlan=False,
    resource=False,
    timeout=False,
    representative=False,
    unexpected=False,
):
    batches = {}
    for device in DEVICES:
        results = []
        for spec in COMMANDS:
            output = baseline_output(device.name, spec.id)

            if stage == BB3_OFF_STAGE:
                if device.name == "DEMO-BB3":
                    output = None
                elif spec.id in {
                    "interface_brief",
                    "link_aggregation_summary",
                    "link_aggregation_verbose",
                    "ospf_peer",
                }:
                    output = DATA["scenarios"]["critical"].get(spec.id, output)
                elif spec.id == "vrrp_status":
                    output = DATA["scenarios"]["unexpected"].get(spec.id, output)

            if stage == CUSTOM_STAGE:
                if vlan:
                    output = DATA["scenarios"]["expected"].get(spec.id, output)

                if resource and spec.id in {"cpu_usage", "memory_usage"}:
                    output = DATA["scenarios"]["critical"].get(spec.id, output)

                if unexpected:
                    output = scenario_output(
                        "unexpected_demo",
                        device.name,
                        spec.id,
                        output,
                    )

                if representative:
                    output = scenario_output(
                        "representative",
                        device.name,
                        spec.id,
                        output,
                    )

                if timeout:
                    output = scenario_output(
                        "collection_failed",
                        device.name,
                        spec.id,
                        output,
                    )

            result = CommandResult.started(device, spec)
            result.success = output is not None
            result.output = output or ""
            result.error_message = (
                "" if result.success else "Synthetic collection timeout"
            )
            results.append(result.finish())
        batches[device.name] = results
    return batches
