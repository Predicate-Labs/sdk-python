"""
CLI commands for Sentience SDK
"""

import argparse
import base64
import shlex
import sys
import time
from pathlib import Path

from .actions import click, press, type_text
from .browser import SentienceBrowser
from .generator import ScriptGenerator
from .inspector import inspect
from .models import SnapshotOptions
from .recorder import Trace, record
from .screenshot import screenshot
from .snapshot import snapshot


def cmd_inspect(args):
    """Start inspector mode"""
    _ = args
    browser = SentienceBrowser(headless=False)
    try:
        browser.start()
        print("✅ Inspector started. Hover elements to see info, click to see full details.")
        print("Press Ctrl+C to stop.")

        with inspect(browser):
            # Keep running until interrupted
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n👋 Inspector stopped.")
    finally:
        browser.close()


def cmd_record(args):
    """Start recording mode"""
    browser = SentienceBrowser(headless=False)
    try:
        browser.start()

        # Navigate to start URL if provided
        if args.url:
            browser.page.goto(args.url)
            browser.page.wait_for_load_state("networkidle")

        print("✅ Recording started. Perform actions in the browser.")
        print("Press Ctrl+C to stop and save trace.")

        with record(browser, capture_snapshots=args.snapshots) as rec:
            # Add mask patterns if provided
            for pattern in args.mask or []:
                rec.add_mask_pattern(pattern)

            # Keep running until interrupted
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n💾 Saving trace...")
                output = args.output or "trace.json"
                rec.save(output)
                print(f"✅ Trace saved to {output}")
    finally:
        browser.close()


def cmd_gen(args):
    """Generate script from trace"""
    # Load trace
    trace = Trace.load(args.trace)

    # Generate script
    generator = ScriptGenerator(trace)

    if args.lang == "py":
        output = args.output or "generated.py"
        generator.save_python(output)
    elif args.lang == "ts":
        output = args.output or "generated.ts"
        generator.save_typescript(output)
    else:
        print(f"❌ Unsupported language: {args.lang}")
        sys.exit(1)

    print(f"✅ Generated {args.lang.upper()} script: {output}")


def _print_driver_help():
    print(
        "\nCommands:\n"
        "  open <url>                 Navigate to URL\n"
        "  state [limit]              List clickable elements (optional limit)\n"
        "  click <element_id>         Click element by id\n"
        "  type <element_id> <text>   Type text into element\n"
        "  press <key>                Press a key (e.g., Enter)\n"
        "  screenshot [path]          Save screenshot (png/jpg)\n"
        "  close                      Close browser and exit\n"
        "  help                       Show this help\n"
    )


def cmd_driver(args):
    """Manual driver CLI for open/state/click/type/screenshot/close."""
    browser = SentienceBrowser(headless=args.headless)
    try:
        browser.start()
        if args.url:
            browser.page.goto(args.url)
            browser.page.wait_for_load_state("networkidle")

        print("✅ Manual driver started. Type 'help' for commands.")

        while True:
            try:
                raw = input("sentience> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Exiting manual driver.")
                break

            if not raw:
                continue

            try:
                parts = shlex.split(raw)
            except ValueError as exc:
                print(f"❌ Parse error: {exc}")
                continue

            cmd = parts[0].lower()
            cmd_args = parts[1:]

            if cmd in {"help", "?"}:
                _print_driver_help()
                continue

            if cmd == "open":
                if not cmd_args:
                    print("❌ Usage: open <url>")
                    continue
                url = cmd_args[0]
                browser.page.goto(url)
                browser.page.wait_for_load_state("networkidle")
                print(f"✅ Opened {url}")
                continue

            if cmd == "state":
                limit = args.limit
                if cmd_args:
                    try:
                        limit = int(cmd_args[0])
                    except ValueError:
                        print("❌ Usage: state [limit]")
                        continue
                snap = snapshot(browser, SnapshotOptions(limit=limit))
                clickables = [
                    el
                    for el in snap.elements
                    if getattr(getattr(el, "visual_cues", None), "is_clickable", False)
                ]
                print(f"URL: {snap.url}")
                print(f"Clickable elements: {len(clickables)}")
                for el in clickables:
                    text = (el.text or "").replace("\n", " ").strip()
                    if len(text) > 60:
                        text = text[:57] + "..."
                    print(f"- id={el.id} role={el.role} text='{text}'")
                continue

            if cmd == "click":
                if len(cmd_args) != 1:
                    print("❌ Usage: click <element_id>")
                    continue
                try:
                    element_id = int(cmd_args[0])
                except ValueError:
                    print("❌ element_id must be an integer")
                    continue
                click(browser, element_id)
                print(f"✅ Clicked element {element_id}")
                continue

            if cmd == "type":
                if len(cmd_args) < 2:
                    print("❌ Usage: type <element_id> <text>")
                    continue
                try:
                    element_id = int(cmd_args[0])
                except ValueError:
                    print("❌ element_id must be an integer")
                    continue
                text = " ".join(cmd_args[1:])
                type_text(browser, element_id, text)
                print(f"✅ Typed into element {element_id}")
                continue

            if cmd == "press":
                if len(cmd_args) != 1:
                    print('❌ Usage: press <key> (e.g., "Enter")')
                    continue
                press(browser, cmd_args[0])
                print(f"✅ Pressed {cmd_args[0]}")
                continue

            if cmd == "screenshot":
                path = cmd_args[0] if cmd_args else None
                if path is None:
                    path = f"screenshot-{int(time.time())}.png"
                out_path = Path(path)
                ext = out_path.suffix.lower()
                fmt = "jpeg" if ext in {".jpg", ".jpeg"} else "png"
                data_url = screenshot(browser, format=fmt)
                _, b64 = data_url.split(",", 1)
                out_path.write_bytes(base64.b64decode(b64))
                print(f"✅ Saved screenshot to {out_path}")
                continue

            if cmd in {"close", "exit", "quit"}:
                print("👋 Closing browser.")
                break

            print(f"❌ Unknown command: {cmd}. Type 'help' for options.")
    finally:
        browser.close()


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="Sentience SDK CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Inspect command
    inspect_parser = subparsers.add_parser("inspect", help="Start inspector mode")
    inspect_parser.set_defaults(func=cmd_inspect)

    # Record command
    record_parser = subparsers.add_parser("record", help="Start recording mode")
    record_parser.add_argument("--url", help="Start URL")
    record_parser.add_argument("--output", "-o", help="Output trace file", default="trace.json")
    record_parser.add_argument(
        "--snapshots", action="store_true", help="Capture snapshots at each step"
    )
    record_parser.add_argument(
        "--mask",
        action="append",
        help="Pattern to mask in recorded text (e.g., password)",
    )
    record_parser.set_defaults(func=cmd_record)

    # Generate command
    gen_parser = subparsers.add_parser("gen", help="Generate script from trace")
    gen_parser.add_argument("trace", help="Trace JSON file")
    gen_parser.add_argument("--lang", choices=["py", "ts"], default="py", help="Output language")
    gen_parser.add_argument("--output", "-o", help="Output script file")
    gen_parser.set_defaults(func=cmd_gen)

    # Manual driver command
    driver_parser = subparsers.add_parser("driver", help="Manual driver CLI")
    driver_parser.add_argument("--url", help="Start URL")
    driver_parser.add_argument("--limit", type=int, default=50, help="Snapshot limit for state")
    driver_parser.add_argument(
        "--headless", action="store_true", help="Run browser in headless mode"
    )
    driver_parser.set_defaults(func=cmd_driver)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
