import io
import plistlib
import zipfile
from pathlib import Path

import pytest

from d11ctl.core import runner
from d11ctl.core.config import Paths
from d11ctl.core.safety import Context, SafetyError, guard_write, verify_target
from d11ctl.modules import bootmon, compat, firmware, usb
from d11ctl.modules.device import DeviceInfo, parse_irecovery

IRECV_DFU = """CPID: 0x8010
CPRV: 0x11
BDID: 0x0e
ECID: 0x001A2B3C4D5E6F
MODE: DFU
PRODUCT: iPhone9,2
MODEL: d11ap
NAME: iPhone 7 Plus
"""


def test_parse_irecovery_dfu():
    d = parse_irecovery(IRECV_DFU)
    assert d.mode == "dfu" and d.cpid == 0x8010 and d.board == "d11ap"
    assert d.ecid == 0x001A2B3C4D5E6F
    verify_target(d)


@pytest.mark.parametrize("dev", [
    DeviceInfo("normal", product_type="iPhone10,2", board="d21ap", cpid=0x8015),
    DeviceInfo("normal", product_type="iPhone9,2", board="d111ap", cpid=0x8010),  # несоответствие
    DeviceInfo("dfu", cpid=0x8010),  # модель не определена
])
def test_verify_rejects(dev):
    with pytest.raises(SafetyError):
        verify_target(dev)


def test_guard_write_dry_run(tmp_path):
    ctx = Context(Paths(tmp_path), dry_run=True)
    assert guard_write(ctx, DeviceInfo("dfu", "iPhone9,4", "d111ap", 0x8010), "test") is False


def test_runner_dry_run_skips_mutating():
    r = runner.run(["definitely-not-a-tool", "--wipe"], mutating=True, dry_run=True)
    assert r.skipped and r.ok


def test_usb_mode_and_serial():
    d = usb.UsbDevice("1-1", 0x05AC, 0x1227, "CPID:8010 CPRV:11 ECID:001A2B3C4D5E6F SRTG:[iBoot-2696.0.0.1.33] PWND:[checkm8]", "")
    assert d.mode == "dfu"
    assert d.serial_fields()["CPID"] == "8010"


def _fake_ipsw(path: Path):
    manifest = {
        "ProductVersion": "15.8.8", "ProductBuildVersion": "19H999",
        "SupportedProductTypes": ["iPhone9,2", "iPhone9,4"],
        "BuildIdentities": [{
            "Info": {"DeviceClass": "d11ap", "Variant": "Customer Erase Install (IPSW)"},
            "Manifest": {
                "KernelCache": {"Info": {"Path": "kernelcache.release.iphone9"}},
                "DeviceTree": {"Info": {"Path": "Firmware/all_flash/DeviceTree.d11ap.im4p"}},
                "SEP": {"Info": {"Path": "Firmware/all_flash/sep-firmware.d11.RELEASE.im4p"}},
                "BasebandFirmware": {"Info": {"Path": "Firmware/Mav-x.bbfw"}},
            },
        }],
    }
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("BuildManifest.plist", plistlib.dumps(manifest))
        z.writestr("kernelcache.release.iphone9", b"KC")
        z.writestr("Firmware/all_flash/DeviceTree.d11ap.im4p", b"DT")


def test_ipsw_summary_and_extract(tmp_path):
    ipsw = tmp_path / "t.ipsw"
    _fake_ipsw(ipsw)
    s = firmware.summary(ipsw)
    assert s["version"] == "15.8.8" and s["identities"][0]["board"] == "d11ap"
    got = firmware.extract(ipsw, "d11ap", ["KernelCache", "DeviceTree", "Nope"], tmp_path / "out")
    assert got["KernelCache"].read_bytes() == b"KC" and "Nope" not in got


def test_verify_hash(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"abc")
    fw = firmware.Firmware("x", "1", "1", "https://x/f", True,
                           sha1="a9993e364706816aba3e25717850c26c9cd0d89d")
    assert firmware.verify(p, fw)
    fw.sha1 = "0" * 40
    assert not firmware.verify(p, fw)


def test_kext_diff_classifies():
    base = {"com.apple.driver.AppleMesaSEPDriver", "com.apple.driver.AppleBasebandPCI", "com.apple.kec.corecrypto"}
    donor = {"com.apple.kec.corecrypto", "com.apple.driver.AppleSomethingNew"}
    d = compat.diff_kexts(base, donor)
    assert d.common == 1
    assert "com.apple.driver.AppleBasebandPCI" in d.only_base["baseband"]
    assert "com.apple.driver.AppleMesaSEPDriver" in d.only_base["touchid_sep"]
    assert "Карта совместимости" in compat.render_markdown(d, None, "a", "b")


def test_dt_diff():
    base = {"name": "device-tree", "children": [
        {"name": "arm-io", "compatible": "arm-io,t8010", "children": [
            {"name": "baseband", "compatible": "baseband,mav"}]}]}
    donor = {"name": "device-tree", "children": [
        {"name": "arm-io", "compatible": "arm-io,t8010", "children": []}]}
    r = compat.diff_dt(compat.flatten_dt(base), compat.flatten_dt(donor))
    assert r["only_base"] == ["/device-tree/arm-io/baseband"]


def test_bootmon_classification():
    log = io.StringIO(
        "iBoot-2696.0.0.1.33\n"
        "Darwin Kernel Version 22.6.0\n"
        "panic(cpu 0 caller 0xfffffff0): SEP panic firmware fail\n")
    r = bootmon.analyze(log)
    assert r["furthest_stage"] == "kernel"
    assert r["verdict"] == "SEP_PANIC"
