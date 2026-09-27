from __future__ import annotations

from drscreen.config import Settings, update_env


def test_update_env_creates_file_and_writes_pairs(tmp_path):
    env_file = tmp_path / ".env"
    assert not env_file.exists()

    update_env({"DRS_CLINIC_NAME": "City Eye Camp", "DRS_REFERRAL_THRESHOLD": "0.4"},
              env_file=env_file)

    text = env_file.read_text()
    assert "DRS_CLINIC_NAME=City Eye Camp" in text
    assert "DRS_REFERRAL_THRESHOLD=0.4" in text


def test_update_env_overwrites_existing_key_without_duplicating(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("DRS_CLINIC_NAME=Old Name\nOTHER_VAR=keep-me\n")

    update_env({"DRS_CLINIC_NAME": "New Name"}, env_file=env_file)

    lines = env_file.read_text().splitlines()
    assert lines.count("DRS_CLINIC_NAME=New Name") == 1
    assert "OTHER_VAR=keep-me" in lines
    assert not any("Old Name" in line for line in lines)


def test_settings_from_env_picks_up_updated_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    update_env({"DRS_CLINIC_NAME": "Custom Clinic", "DRS_REFERRAL_THRESHOLD": "0.35"},
              env_file=env_file)

    for var in ("DRS_CLINIC_NAME", "DRS_REFERRAL_THRESHOLD"):
        monkeypatch.delenv(var, raising=False)

    settings = Settings.from_env(env_file=env_file)

    assert settings.clinic_name == "Custom Clinic"
    assert settings.referral_threshold == 0.35
