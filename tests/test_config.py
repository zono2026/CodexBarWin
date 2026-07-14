import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config


def test_load_config_creates_default_when_missing(tmp_path):
    config_path = tmp_path / "config.json"
    assert not config_path.exists()

    loaded = config.load_config(config_path=str(config_path))

    assert loaded["poll_interval_minutes"] == config.DEFAULT_POLL_INTERVAL_MINUTES
    assert config_path.exists()


def test_load_config_reads_existing_value(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"poll_interval_minutes": 15}))

    loaded = config.load_config(config_path=str(config_path))

    assert loaded["poll_interval_minutes"] == 15


def test_load_config_falls_back_to_default_on_invalid_value(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"poll_interval_minutes": 999}))

    loaded = config.load_config(config_path=str(config_path))

    assert loaded["poll_interval_minutes"] == config.DEFAULT_POLL_INTERVAL_MINUTES


def test_load_config_falls_back_to_default_on_malformed_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("not json")

    loaded = config.load_config(config_path=str(config_path))

    assert loaded["poll_interval_minutes"] == config.DEFAULT_POLL_INTERVAL_MINUTES


def test_set_poll_interval_persists_value(tmp_path):
    config_path = tmp_path / "config.json"

    updated = config.set_poll_interval(5, config_path=str(config_path))
    assert updated["poll_interval_minutes"] == 5

    reloaded = config.load_config(config_path=str(config_path))
    assert reloaded["poll_interval_minutes"] == 5


def test_set_poll_interval_rejects_disallowed_value(tmp_path):
    config_path = tmp_path / "config.json"

    try:
        config.set_poll_interval(999, config_path=str(config_path))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_load_config_falls_back_to_default_when_json_is_not_an_object(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps([1, 2, 3]))

    loaded = config.load_config(config_path=str(config_path))

    assert loaded["poll_interval_minutes"] == config.DEFAULT_POLL_INTERVAL_MINUTES


def test_load_config_includes_default_background_color_when_missing(tmp_path):
    config_path = tmp_path / "config.json"

    loaded = config.load_config(config_path=str(config_path))

    assert loaded["background_color"] == config.DEFAULT_BACKGROUND_COLOR


def test_load_config_reads_existing_background_color(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"background_color": "#336699"}))

    loaded = config.load_config(config_path=str(config_path))

    assert loaded["background_color"] == "#336699"


def test_load_config_falls_back_to_default_on_invalid_background_color(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"background_color": "not-a-color"}))

    loaded = config.load_config(config_path=str(config_path))

    assert loaded["background_color"] == config.DEFAULT_BACKGROUND_COLOR


def test_set_background_color_persists_value(tmp_path):
    config_path = tmp_path / "config.json"

    updated = config.set_background_color("#112233", config_path=str(config_path))
    assert updated["background_color"] == "#112233"

    reloaded = config.load_config(config_path=str(config_path))
    assert reloaded["background_color"] == "#112233"


def test_set_background_color_rejects_invalid_format(tmp_path):
    config_path = tmp_path / "config.json"

    try:
        config.set_background_color("blue", config_path=str(config_path))
        assert False, "expected ValueError"
    except ValueError:
        pass
