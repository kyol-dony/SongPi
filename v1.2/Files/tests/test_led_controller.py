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
