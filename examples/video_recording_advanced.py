"""
Advanced Video Recording Demo

Demonstrates advanced video recording features:
- Custom resolution (1080p)
- Custom output filename
- Multiple recordings in one session
"""

from datetime import datetime
from pathlib import Path

from sentience import SentienceBrowser


def main():
    print("\n" + "=" * 60)
    print("Advanced Video Recording Demo")
    print("=" * 60 + "\n")

    video_dir = Path("./recordings")
    video_dir.mkdir(exist_ok=True)

    # Example 1: Custom Resolution (1080p)
    print("📹 Example 1: Recording in 1080p (Full HD)\n")

    with SentienceBrowser(
        record_video_dir=str(video_dir),
        record_video_size={"width": 1920, "height": 1080},  # 1080p resolution
    ) as browser:
        print("   Resolution: 1920x1080")
        browser.page.goto("https://example.com")
        browser.page.wait_for_load_state("networkidle")
        browser.page.wait_for_timeout(2000)

        # Close with custom filename
        video_path = browser.close(output_path=video_dir / "example_1080p.webm")
        print(f"   ✅ Saved: {video_path}\n")

    # Example 2: Custom Filename with Timestamp
    print("📹 Example 2: Recording with timestamp filename\n")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    custom_filename = f"recording_{timestamp}.webm"

    with SentienceBrowser(record_video_dir=str(video_dir)) as browser:
        browser.page.goto("https://example.com")
        browser.page.click("text=More information")
        browser.page.wait_for_timeout(2000)

        video_path = browser.close(output_path=video_dir / custom_filename)
        print(f"   ✅ Saved: {video_path}\n")

    # Example 3: Organized by Project
    print("📹 Example 3: Organized directory structure\n")

    project_dir = Path("./recordings/my_project/tutorials")

    with SentienceBrowser(record_video_dir=str(project_dir)) as browser:
        print(f"   Saving to: {project_dir}")
        browser.page.goto("https://example.com")
        browser.page.wait_for_timeout(2000)

        video_path = browser.close(output_path=project_dir / "tutorial_01.webm")
        print(f"   ✅ Saved: {video_path}\n")

    # Example 4: Multiple videos with descriptive names
    print("📹 Example 4: Tutorial series with descriptive names\n")

    tutorials = [
        ("intro", "https://example.com"),
        ("navigation", "https://example.com"),
        ("features", "https://example.com"),
    ]

    for name, url in tutorials:
        with SentienceBrowser(record_video_dir=str(video_dir)) as browser:
            browser.page.goto(url)
            browser.page.wait_for_timeout(1000)

            video_path = browser.close(output_path=video_dir / f"{name}.webm")
            print(f"   ✅ {name}: {video_path}")

    print("\n" + "=" * 60)
    print("All recordings completed!")
    print(f"Check {video_dir.absolute()} for all videos")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
