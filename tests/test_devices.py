from mobiflow.devices import _parse_adb_devices, _parse_simctl_all, host_capabilities


def test_parse_adb_devices():
    out = _parse_adb_devices(
        "List of devices attached\nemulator-5554\tdevice\nR58M123\tdevice\n"
    )
    assert len(out) == 2
    assert out[0]["id"] == "emulator-5554"
    assert out[0]["kind"] == "emulator"
    assert out[1]["kind"] == "device"


def test_parse_simctl_all():
    text = """\
== Devices ==
-- iOS 18.0 --
    iPhone 16 (AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE) (Shutdown)
    iPhone 15 (FFFFFFFF-0000-1111-2222-333333333333) (Booted)
"""
    sims = _parse_simctl_all(text)
    assert len(sims) == 2
    booted = [s for s in sims if s["state"] == "online"]
    avail = [s for s in sims if s["state"] == "available"]
    assert len(booted) == 1
    assert len(avail) == 1
    assert avail[0]["startable"] == "true"


def test_host_capabilities_shape():
    caps = host_capabilities()
    assert "os" in caps
    assert "can_start_android" in caps
    assert "can_start_ios" in caps
