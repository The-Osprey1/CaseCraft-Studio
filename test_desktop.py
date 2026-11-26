"""Desktop-app support: frozen/unfrozen paths, robust preset loading, the user device library,
the access token, request limits, error ids, project files and atomic writes. All fast (no CAD)."""
import copy
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import appdirs
import projects
import server

PRESETS = Path(__file__).parent / "presets"


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "userdata"
    monkeypatch.setenv("CASECRAFT_DATA_DIR", str(d))
    return d


@pytest.fixture()
def client(data_dir, monkeypatch):
    monkeypatch.setattr(server, "ACCESS_TOKEN", None)
    return TestClient(server.app, raise_server_exceptions=False)


def _preset(pid="iphone_15_pro") -> dict:
    return json.loads((PRESETS / f"{pid}.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ paths
def test_resource_dir_source_checkout():
    assert appdirs.resource_dir() == Path(appdirs.__file__).resolve().parent
    assert not appdirs.is_frozen()


def test_resource_dir_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert appdirs.is_frozen()
    assert appdirs.resource_dir() == tmp_path


def test_user_dirs_follow_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("CASECRAFT_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("CASECRAFT_LOG_DIR", str(tmp_path / "l"))
    assert appdirs.user_presets_dir() == tmp_path / "d" / "presets" and (tmp_path / "d" / "presets").is_dir()
    assert appdirs.log_dir() == tmp_path / "l"


def test_appdata_default(monkeypatch, tmp_path):
    monkeypatch.delenv("CASECRAFT_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert appdirs.user_data_dir(create=False) == tmp_path / "CaseCraft Studio"


# ------------------------------------------------------------------ atomic writes
def test_atomic_write_keeps_old_file_on_failure(tmp_path, monkeypatch):
    target = tmp_path / "f.json"
    appdirs.atomic_write_text(target, "good")

    def boom(*_a, **_k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(appdirs.os, "replace", boom)
    with pytest.raises(OSError):
        appdirs.atomic_write_text(target, "half-written")
    assert target.read_text() == "good"
    assert [p.name for p in tmp_path.iterdir()] == ["f.json"]      # no temp file left behind


def test_read_json_tolerates_corrupt_and_missing(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert appdirs.read_json(bad, {"d": 1}) == {"d": 1}
    assert appdirs.read_json(tmp_path / "missing.json", []) == []


# ------------------------------------------------------------------ presets endpoint robustness
def test_bad_preset_file_is_skipped_not_fatal(client, monkeypatch, tmp_path):
    builtin = tmp_path / "presets"
    builtin.mkdir()
    (builtin / "iphone_15_pro.json").write_text(json.dumps(_preset()), encoding="utf-8")
    (builtin / "broken.json").write_text("{oops", encoding="utf-8")
    monkeypatch.setattr(server, "PRESETS_DIR", builtin)
    r = client.get("/api/presets")
    assert r.status_code == 200
    data = r.json()
    assert [p["id"] for p in data["presets"]] == ["iphone_15_pro"]
    assert data["skipped"][0]["file"] == "broken.json"
    assert data["default_id"] == "iphone_15_pro"


def test_presets_payload_round_trips_through_preset_parser(client):
    """The UI sends a preset straight back as a design; extra metadata must not be in it."""
    for p in client.get("/api/presets").json()["presets"]:
        server.Preset.from_dict(copy.deepcopy(p))


# ------------------------------------------------------------------ user device library
def test_user_preset_round_trip(client, data_dir):
    p = _preset()
    p.update(id="my_phone", name="My Phone")
    r = client.post("/api/user-presets", json=p)
    assert r.status_code == 200, r.text
    assert (data_dir / "presets" / "my_phone.json").is_file()
    listing = client.get("/api/presets").json()
    assert "my_phone" in listing["user_ids"]
    assert any(x["id"] == "my_phone" for x in listing["presets"])
    assert client.delete("/api/user-presets/my_phone").status_code == 200
    assert "my_phone" not in client.get("/api/presets").json()["user_ids"]
    assert client.delete("/api/user-presets/my_phone").status_code == 404


def test_user_preset_cannot_shadow_builtin(client):
    r = client.post("/api/user-presets", json=_preset("iphone_15_pro"))
    assert r.status_code == 409


@pytest.mark.parametrize("bad_id", ["../evil", "UPPER", "with space", "a" * 65, ""])
def test_user_preset_rejects_unsafe_ids(client, bad_id):
    p = _preset()
    p["id"] = bad_id
    assert client.post("/api/user-presets", json=p).status_code == 422


def test_user_preset_delete_rejects_traversal(client, data_dir):
    victim = data_dir / "settings.json"
    victim.parent.mkdir(parents=True, exist_ok=True)
    victim.write_text("{}", encoding="utf-8")
    for url in ("/api/user-presets/..%2Fsettings", "/api/user-presets/..", "/api/user-presets/settings.json"):
        assert client.delete(url).status_code in (404, 405, 422), url
    assert victim.exists()


def test_invalid_user_preset_rejected(client):
    p = _preset()
    p.update(id="my_bad")
    p["body"]["length"] = -5
    assert client.post("/api/user-presets", json=p).status_code == 422


def test_corrupt_user_preset_is_skipped(client, data_dir):
    (data_dir / "presets").mkdir(parents=True, exist_ok=True)
    (data_dir / "presets" / "my_broken.json").write_text("[]", encoding="utf-8")
    data = client.get("/api/presets").json()
    assert any(s["file"] == "my_broken.json" for s in data["skipped"])
    assert len(data["presets"]) == len(list(PRESETS.glob("*.json")))   # every built-in still listed


# ------------------------------------------------------------------ token + limits + errors
def test_token_required_in_desktop_mode(client, monkeypatch):
    monkeypatch.setattr(server, "ACCESS_TOKEN", "secret-token")
    assert client.get("/api/presets").status_code == 403
    assert client.get("/presets").status_code == 403
    assert client.get("/api/presets", headers={"X-CaseCraft-Token": "wrong"}).status_code == 403
    assert client.get("/api/presets", headers={"X-CaseCraft-Token": "secret-token"}).status_code == 200
    assert client.get("/api/presets?token=secret-token").status_code == 200
    assert client.get("/api/health").status_code == 200          # startup polling stays open


def test_oversized_request_rejected(client):
    r = client.post("/api/generate-preview", content=b"x",
                    headers={"Content-Type": "application/json",
                             "Content-Length": str(server.MAX_BODY_BYTES + 1)})
    assert r.status_code == 413


def test_unexpected_error_has_error_id(client, monkeypatch):
    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(server, "PRINTERS", type("X", (), {"values": staticmethod(boom)})())
    r = client.get("/api/printers")
    assert r.status_code == 500
    assert "error id" in r.json()["detail"] and "kaboom" in r.json()["detail"]


def test_health_reports_version(client):
    from version import __version__
    assert client.get("/api/health").json() == {"status": "ok", "version": __version__}


# ------------------------------------------------------------------ project files
def _project():
    return {"format": "casecraft-project", "version": 1, "name": "test", "config": _preset(),
            "printerId": "generic_256", "colors": {"frame": "#000000"}}


def test_project_round_trip(tmp_path):
    path = tmp_path / "a.casecraft"
    path.write_text(projects.dump_project(_project()), encoding="utf-8")
    assert projects.load_project(path)["config"]["id"] == "iphone_15_pro"


@pytest.mark.parametrize("content, msg", [
    ("{broken", "damaged"),
    (json.dumps(_preset()), "not a CaseCraft project"),
    (json.dumps({"format": "casecraft-project", "version": 99, "config": {"id": "x"}}), "newer"),
    (json.dumps({"format": "casecraft-project", "version": 1}), "no valid design"),
    (json.dumps([1, 2]), "expected a JSON object"),
])
def test_project_errors_are_readable(tmp_path, content, msg):
    path = tmp_path / "bad.casecraft"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(projects.ProjectError, match=msg):
        projects.load_project(path)


def test_project_missing_and_binary(tmp_path):
    with pytest.raises(projects.ProjectError, match="Cannot open"):
        projects.load_project(tmp_path / "nope.casecraft")
    binf = tmp_path / "bin.casecraft"
    binf.write_bytes(b"\xff\xfe\x00\x81" * 10)
    with pytest.raises(projects.ProjectError):
        projects.load_project(binf)


def test_project_bom_tolerated(tmp_path):
    path = tmp_path / "bom.casecraft"
    path.write_bytes(b"\xef\xbb\xbf" + projects.dump_project(_project()).encode("utf-8"))
    assert projects.load_project(path)["name"] == "test"


def test_recent_list_dedupes_case_insensitively_and_caps():
    recent = []
    for i in range(15):
        recent = projects.push_recent(recent, f"C:/p/{i}.casecraft")
    assert len(recent) == projects.MAX_RECENT
    recent = projects.push_recent(recent, "c:/P/14.CASECRAFT")
    assert len(recent) == projects.MAX_RECENT and recent[0].lower().endswith("14.casecraft")
    assert sum(r.lower() == str(Path("c:/p/14.casecraft")).lower() for r in recent) == 1


# ------------------------------------------------------------------ window placement (desktop/app.py)
def _app_module():
    sys.path.insert(0, str(Path(__file__).parent / "desktop"))
    import importlib
    return importlib.import_module("app")


def test_first_launch_window_is_centred_on_primary():
    app = _app_module()
    g = app.initial_geometry({}, [(0, 0, 2048, 1152)])
    assert (g["width"], g["height"]) == (1440, 900)
    assert 0 <= g["x"] and g["x"] + g["width"] <= 2048
    assert 0 <= g["y"] and g["y"] + g["height"] <= 1152


def test_window_fits_small_screen():
    app = _app_module()
    g = app.initial_geometry({"window": {"width": 3000, "height": 2000}}, [(0, 0, 1280, 720)])
    assert g["width"] <= 1280 and g["height"] <= 720 and g["x"] >= 0 and g["y"] >= 0


def test_saved_position_on_missing_monitor_is_discarded():
    app = _app_module()
    saved = {"window": {"x": 3000, "y": 200, "width": 1200, "height": 800}}     # second monitor unplugged
    g = app.initial_geometry(saved, [(0, 0, 1920, 1080)])
    assert g["x"] + g["width"] <= 1920
    g2 = app.initial_geometry(saved, [(0, 0, 1920, 1080), (1920, 0, 2560, 1440)])
    assert g2["x"] == 3000                                                  # still there: reused


@pytest.mark.parametrize("bad", [{"window": "junk"}, {"window": {"x": "a", "width": None}}, {"window": {"x": -32000, "y": -32000}}])
def test_corrupt_window_settings_are_ignored(bad):
    app = _app_module()
    g = app.initial_geometry(bad, [(0, 0, 1920, 1080)])
    assert 0 <= g["x"] < 1920 and 0 <= g["y"] < 1080
