"""Render the current Tk app with its built-in synthetic comparison; never collect."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from capture_windows import (
    block_network,
    capture_window,
    prepare_capture_desktop,
    write_manifest,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    prepare_capture_desktop()
    block_network()
    from core import gui
    from core.models import Device
    from core.version import APP_VERSION

    with tempfile.TemporaryDirectory(prefix="hpe-docs-") as directory:
        runtime = Path(directory)
        gui.PROJECT_DIR = runtime
        gui.CONFIG_DIR = runtime / "config"
        gui.OUTPUT_DIR = runtime / "outputs" / "snapshots"
        gui.COMMANDS_PATH = gui.CONFIG_DIR / "commands.yaml"
        gui.DEVICES_PATH = gui.CONFIG_DIR / "devices.yaml"
        gui.DEVICES_EXAMPLE_PATH = gui.CONFIG_DIR / "devices.example.yaml"
        gui.ANALYSIS_RULES_PATH = gui.CONFIG_DIR / "analysis_rules.yaml"
        gui.KNOWN_HOSTS_PATH = gui.CONFIG_DIR / "known_hosts"
        app = gui.BackboneStateTrackerApp()
        try:
            app.maxsize(1920, 1400)
            app.geometry("1400x1000+0+0")
            app.update()
            assert app.winfo_width() >= 1300 and app.winfo_height() >= 950, (
                app.geometry()
            )
            app._apply_devices(
                [
                    Device(name="backbone3", host="192.0.2.3"),
                    Device(name="backbone4", host="192.0.2.4"),
                ]
            )
            app.username_var.set("netops-demo")
            app.password_var.set("documentation-only")
            app.status_chip_var.set("합성 예제 · 장비 접속 없음")
            capture_window(app, output / "settings-collection.png")
            # Product's actual sample generator, DiffEngine, report writer and GUI adapter.
            app.create_mock_validation()
            assert app.last_diff_summary is not None
            assert app.latest_report is not None and app.latest_report.is_file()
            capture_window(app, output / "compare-results.png")
            rows = app.diff_tree.get_children()
            assert rows, "Built-in sample must produce visible changes"
            app.diff_tree.selection_set(rows[0])
            app._on_diff_detail_selected(None)
            capture_window(app, output / "selected-change.png")
            # Keep generated paths recognizable without exposing runner-local directories.
            logs = app.log_text.get("1.0", "end").replace(str(runtime), "DEMO_RUNTIME")
            app.log_text.configure(state="normal")
            app.log_text.delete("1.0", "end")
            app.log_text.insert("1.0", logs)
            app.show_page("logs")
            capture_window(app, output / "work-log.png")
            write_manifest(
                output,
                app="HPE Comware Change Validator",
                version=APP_VERSION,
                method="Actual Tk window / PrintWindow; built-in synthetic sample -> DiffEngine -> report -> GUI; runtime paths displayed as DEMO_RUNTIME",
            )
        finally:
            app.destroy()


if __name__ == "__main__":
    main()
