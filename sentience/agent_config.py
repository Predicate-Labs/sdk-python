"""
Configuration classes for Sentience agents.
"""

from dataclasses import dataclass


@dataclass
class AgentConfig:
    """
    Configuration for Sentience Agent execution.

    This dataclass provides centralized configuration for agent behavior,
    including snapshot limits, retry logic, verification, and screenshot capture.

    Attributes:
        snapshot_limit: Maximum elements to include in LLM context (default: 50)
        temperature: LLM temperature 0.0-1.0 for response generation (default: 0.0)
        max_retries: Number of retries on action failure (default: 1)
        verify: Whether to run verification step after actions (default: True)
        capture_screenshots: Whether to capture screenshots during execution (default: True)
        screenshot_format: Screenshot format 'png' or 'jpeg' (default: 'jpeg')
        screenshot_quality: JPEG quality 1-100, ignored for PNG (default: 80)

    Example:
        >>> from sentience import AgentConfig, SentienceAgent
        >>> config = AgentConfig(
        ...     snapshot_limit=100,
        ...     max_retries=2,
        ...     verify=True
        ... )
        >>> agent = SentienceAgent(browser, llm, config=config)
    """

    snapshot_limit: int = 50
    temperature: float = 0.0
    max_retries: int = 1
    verify: bool = True

    # Screenshot options
    capture_screenshots: bool = True
    screenshot_format: str = "jpeg"  # "png" or "jpeg"
    screenshot_quality: int = 80  # 1-100 (for JPEG only)
