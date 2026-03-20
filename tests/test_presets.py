import json, os, tempfile
import pytest
import downloader.presets as m

def test_defaults_returned_when_no_file(tmp_path, monkeypatch):
    preset_path = str(tmp_path / ".ytdl_presets.json")
    monkeypatch.setattr(m, "PRESETS_PATH", preset_path)
    presets = m.load_presets()
    assert len(presets) == 3
    assert presets[0]["name"] == "Music 320"

def test_save_and_reload(tmp_path, monkeypatch):
    preset_file = tmp_path / ".ytdl_presets.json"
    preset_path = str(preset_file)
    monkeypatch.setattr(m, "PRESETS_PATH", preset_path)
    custom = [{"name": "Test", "format_type": "audio", "codec": "mp3", "quality": "128"}]
    m.save_presets(custom)
    assert preset_file.exists()
    loaded = m.load_presets()
    assert loaded[0]["name"] == "Test"
