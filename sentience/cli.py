"""
CLI commands for Sentience SDK
"""

import argparse
import sys
from pathlib import Path
from .browser import SentienceBrowser
from .inspector import inspect
from .recorder import record
from .generator import ScriptGenerator
from .recorder import Trace


def cmd_inspect(args):
    """Start inspector mode"""
    browser = SentienceBrowser(headless=False)
    try:
        browser.start()
        print("✅ Inspector started. Hover elements to see info, click to see full details.")
        print("Press Ctrl+C to stop.")
        
        with inspect(browser):
            # Keep running until interrupted
            import time
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
            import time
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
        code = generator.generate_python()
        output = args.output or "generated.py"
        generator.save_python(output)
    elif args.lang == "ts":
        code = generator.generate_typescript()
        output = args.output or "generated.ts"
        generator.save_typescript(output)
    else:
        print(f"❌ Unsupported language: {args.lang}")
        sys.exit(1)
    
    print(f"✅ Generated {args.lang.upper()} script: {output}")


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
    record_parser.add_argument("--snapshots", action="store_true", help="Capture snapshots at each step")
    record_parser.add_argument("--mask", action="append", help="Pattern to mask in recorded text (e.g., password)")
    record_parser.set_defaults(func=cmd_record)
    
    # Generate command
    gen_parser = subparsers.add_parser("gen", help="Generate script from trace")
    gen_parser.add_argument("trace", help="Trace JSON file")
    gen_parser.add_argument("--lang", choices=["py", "ts"], default="py", help="Output language")
    gen_parser.add_argument("--output", "-o", help="Output script file")
    gen_parser.set_defaults(func=cmd_gen)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()

