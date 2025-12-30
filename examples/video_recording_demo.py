"""
Video Recording Demo - Record browser sessions with SentienceBrowser

This example demonstrates how to use the video recording feature
to capture browser automation sessions.
"""

from sentience import SentienceBrowser
from pathlib import Path


def main():
    # Create output directory for videos
    video_dir = Path("./recordings")
    video_dir.mkdir(exist_ok=True)

    print("\n" + "=" * 60)
    print("Video Recording Demo")
    print("=" * 60 + "\n")

    # Create browser with video recording enabled
    with SentienceBrowser(record_video_dir=str(video_dir)) as browser:
        print("🎥 Video recording enabled")
        print(f"📁 Videos will be saved to: {video_dir.absolute()}\n")

        # Navigate to example.com
        print("Navigating to example.com...")
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")

        # Perform some actions
        print("Taking screenshot...")
        browser.page.screenshot(path="example_screenshot.png")

        print("Scrolling page...")
        browser.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        browser.page.wait_for_timeout(1000)

        print("\n✅ Recording complete!")
        print("Video will be saved when browser closes...\n")

    # Video is automatically saved when context manager exits
    print("=" * 60)
    print(f"Check {video_dir.absolute()} for the recorded video (.webm)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
