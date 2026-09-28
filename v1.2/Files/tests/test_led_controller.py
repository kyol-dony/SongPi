from led_controller import LedController, hex_to_rgb


def test_hex_to_rgb_accepts_hash_or_plain_hex():
    assert hex_to_rgb("#7c8fff") == (124, 143, 255)
    assert hex_to_rgb("ff8000") == (255, 128, 0)


def test_hex_to_rgb_rejects_invalid_values():
    import pytest
    with pytest.raises(ValueError):
        hex_to_rgb("blue")


def test_controller_is_disabled_without_configuration():
    controller = LedController()
    assert controller.is_configured is False
    assert controller.set_track_color("#7c8fff") is False


def test_controller_clamps_brightness():
    assert LedController({"enabled": True, "port": "COM3", "brightness": 300}).brightness == 255


def test_controller_defaults_to_uno_reset_delay():
    assert LedController().reset_delay_seconds == 2.0


def test_transport_failure_clears_queued_color_cache():
    controller = LedController({"enabled": True, "port": "test"})
    controller._last_color = (12, 34, 56)
    controller._last_state = "ready"
    controller._pending_commands = ["COLOR 12 34 56"]

    controller._close_unlocked()

    assert controller._last_color is None
    assert controller._last_state is None
    assert controller._pending_commands == []
