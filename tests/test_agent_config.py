"""Tests for sentience.agent_config module"""

from sentience.agent_config import AgentConfig


def test_agent_config_defaults():
    """Test AgentConfig with default values."""
    config = AgentConfig()

    assert config.snapshot_limit == 50
    assert config.temperature == 0.0
    assert config.max_retries == 1
    assert config.verify is True
    assert config.capture_screenshots is True
    assert config.screenshot_format == "jpeg"
    assert config.screenshot_quality == 80


def test_agent_config_custom_values():
    """Test AgentConfig with custom values."""
    config = AgentConfig(
        snapshot_limit=100,
        temperature=0.5,
        max_retries=3,
        verify=False,
        capture_screenshots=False,
        screenshot_format="png",
        screenshot_quality=95,
    )

    assert config.snapshot_limit == 100
    assert config.temperature == 0.5
    assert config.max_retries == 3
    assert config.verify is False
    assert config.capture_screenshots is False
    assert config.screenshot_format == "png"
    assert config.screenshot_quality == 95


def test_agent_config_partial_override():
    """Test AgentConfig with partial overrides."""
    config = AgentConfig(
        snapshot_limit=200,
        max_retries=5,
    )

    # Overridden values
    assert config.snapshot_limit == 200
    assert config.max_retries == 5

    # Default values
    assert config.temperature == 0.0
    assert config.verify is True
    assert config.capture_screenshots is True
    assert config.screenshot_format == "jpeg"
    assert config.screenshot_quality == 80


def test_agent_config_temperature_range():
    """Test AgentConfig accepts valid temperature range."""
    config_low = AgentConfig(temperature=0.0)
    config_mid = AgentConfig(temperature=0.5)
    config_high = AgentConfig(temperature=1.0)

    assert config_low.temperature == 0.0
    assert config_mid.temperature == 0.5
    assert config_high.temperature == 1.0


def test_agent_config_screenshot_quality_range():
    """Test AgentConfig accepts valid screenshot quality range."""
    config_low = AgentConfig(screenshot_quality=1)
    config_mid = AgentConfig(screenshot_quality=50)
    config_high = AgentConfig(screenshot_quality=100)

    assert config_low.screenshot_quality == 1
    assert config_mid.screenshot_quality == 50
    assert config_high.screenshot_quality == 100


def test_agent_config_screenshot_formats():
    """Test AgentConfig accepts both screenshot formats."""
    config_jpeg = AgentConfig(screenshot_format="jpeg")
    config_png = AgentConfig(screenshot_format="png")

    assert config_jpeg.screenshot_format == "jpeg"
    assert config_png.screenshot_format == "png"


def test_agent_config_immutability():
    """Test that AgentConfig is a dataclass and can be modified."""
    config = AgentConfig()

    # Dataclasses are mutable by default
    config.snapshot_limit = 200
    assert config.snapshot_limit == 200

    config.verify = False
    assert config.verify is False


def test_agent_config_repr():
    """Test AgentConfig has a readable representation."""
    config = AgentConfig(snapshot_limit=100, temperature=0.5)

    repr_str = repr(config)
    assert "AgentConfig" in repr_str
    assert "snapshot_limit=100" in repr_str
    assert "temperature=0.5" in repr_str


def test_agent_config_equality():
    """Test AgentConfig equality comparison."""
    config1 = AgentConfig(snapshot_limit=100, temperature=0.5)
    config2 = AgentConfig(snapshot_limit=100, temperature=0.5)
    config3 = AgentConfig(snapshot_limit=200, temperature=0.5)

    assert config1 == config2
    assert config1 != config3
