"""Cache invalidation and USB worker correctness without hardware."""
import errno
import io
import os
import threading
import zipfile

import pytest
from PIL import Image

from d200x_button_box import config, device, layout, widgets, protocol


@pytest.fixture(autouse=True)
def empty_layout_caches():
    layout.clear_caches()
    yield
    layout.clear_caches()


def test_page_cache_reuses_zip_and_invalidates_edits(monkeypatch):
    page = config.Page(keys={0: {"label": "First"}})
    first = layout.build_set_buttons(page)
    original = layout._cell_icon
    calls = []
    def render(*args):
        calls.append(args[1])
        return original(*args)
    monkeypatch.setattr(layout, "_cell_icon", render)
    assert layout.build_set_buttons(page) is first
    assert not calls
    page.keys[0]["label"] = "Second"
    assert layout.build_set_buttons(page) != first
    assert calls == [0]  # unchanged cells keep their rendered PNGs


def test_asset_replacement_invalidates_page_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    icons = tmp_path / "icons"
    icons.mkdir()
    path = icons / "custom.png"
    Image.new("RGB", (196, 196), "red").save(path)
    page = config.Page(keys={0: {"icon": "custom.png"}})
    first = layout.build_set_buttons(page)
    Image.new("RGB", (196, 196), "blue").save(path)
    assert layout.build_set_buttons(page) != first


def test_widget_keeps_refreshing_while_static_cells_are_cached(monkeypatch):
    page = config.Page(keys={0: {"label": "Static"}, 13: {"widget": "clock"}})
    def png(colour):
        buf = io.BytesIO()
        Image.new("RGB", (196, 100), colour).save(buf, "PNG")
        return buf.getvalue()
    renders = iter([png("red"), png("blue")])
    monkeypatch.setattr(widgets, "render", lambda *args: next(renders))
    first = layout.build_set_buttons(page)
    second = layout.build_set_buttons(page)
    assert first != second
    assert len(layout._ICON_CACHE) == 13


def test_padding_is_leading_safe_and_deterministic():
    page = config.default_profile("default").page(0)
    first = layout.build_set_buttons(page)
    assert layout._payload_safe(first)
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.testzip() is None
        assert "manifest.json" in archive.namelist()
        if "dummy.txt" in archive.namelist():
            assert archive.namelist()[0] == "dummy.txt"
    layout.clear_caches()
    assert layout.build_set_buttons(page) == first


def test_failed_upload_does_not_record_layout_hash():
    dev = device.Device.__new__(device.Device)
    def failed_write(payload):
        raise device.DeviceGone("unplugged")
    dev._write = failed_write
    with pytest.raises(device.DeviceGone):
        dev.send_init(config.Page(keys={0: {"label": "Test"}}))
    assert not hasattr(dev, "_layout_hash")


def test_transient_write_retries_same_report(monkeypatch):
    dev = device.Device.__new__(device.Device)
    dev._fd = 99
    calls = []
    def write(fd, payload):
        calls.append(payload)
        if len(calls) == 1:
            raise BlockingIOError(errno.EAGAIN, "busy")
        return len(payload)
    monkeypatch.setattr(device.os, "write", write)
    dev._write(b"report")
    assert calls == [b"report", b"report"]


def test_short_report_is_failure(monkeypatch):
    dev = device.Device.__new__(device.Device)
    dev._fd = 99
    monkeypatch.setattr(device.os, "write", lambda fd, data: 2)
    with pytest.raises(device.DeviceGone, match="short HID write"):
        dev._write(b"report")


def make_device(monkeypatch):
    monkeypatch.setattr(device, "find_hidraw", lambda: "/dev/null")
    return device.Device()


def test_worker_serializes_bundles_and_uses_latest_page(monkeypatch):
    dev = make_device(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    writes = []
    main_thread = threading.get_ident()
    def write(fd, data):
        writes.append((data, threading.get_ident()))
        if len(writes) == 1:
            entered.set()
            assert release.wait(2)
        return len(data)
    monkeypatch.setattr(device.os, "write", write)
    # Make packet contents identify which immutable page snapshot was uploaded.
    monkeypatch.setattr(layout, "build_set_buttons", lambda page, *a, **k: (page.keys[0]["label"] + "|").encode() * 500)
    dev.start_writer()
    try:
        dev.send_init(config.Page(keys={0: {"label": "first"}}))
        assert entered.wait(1)
        dev.send_init(config.Page(keys={0: {"label": "discarded"}}))
        page = config.Page(keys={0: {"label": "latest"}})
        dev.send_init(page)
        page.keys[0]["label"] = "mutated"
        dev.set_brightness(42)
        release.set()
        dev.wait_idle()
        first = [b"\x00" + p for p in protocol.frame_packets(protocol.CMD_SET_BUTTONS, b"first|" * 500)]
        latest = [b"\x00" + p for p in protocol.frame_packets(protocol.CMD_SET_BUTTONS, b"latest|" * 500)]
        assert [data for data, _ in writes] == first + latest + [b"\x00" + protocol.build_brightness(42)]
        assert all(identity != main_thread for _, identity in writes)
    finally:
        release.set()
        dev.close()


def test_worker_drops_widget_updates_from_superseded_page(monkeypatch):
    dev = make_device(monkeypatch)
    entered, release = threading.Event(), threading.Event()
    jobs = []
    dev.start_writer()
    try:
        def block():
            entered.set()
            assert release.wait(2)
        dev._submit("control:block", block)
        assert entered.wait(1)
        dev._submit("partial", lambda: jobs.append("stale"), generation=dev._generation)
        dev._submit("layout", lambda: jobs.append("latest"))
        release.set()
        dev.wait_idle()
        assert jobs == ["latest"]
    finally:
        release.set()
        dev.close()


def test_worker_error_is_seen_by_input_loop(monkeypatch):
    dev = make_device(monkeypatch)
    dev.start_writer()
    try:
        def failed():
            raise device.DeviceGone("device unplugged")
        dev._submit("layout", failed)
        with pytest.raises(device.DeviceGone, match="unplugged"):
            dev.wait_idle()
        with pytest.raises(device.DeviceGone, match="unplugged"):
            dev.read_raw()
    finally:
        dev.close()
