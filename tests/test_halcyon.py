import plistlib
import zipfile

import pytest

from halcyon import cli
from halcyon.modules import bootmon, build, compat, devicetree, img4, panic
from halcyon.modules.device import detect
from halcyon.modules.firmware import IPSW
from halcyon.modules.safety import Guard, SafetyError, require_ipsw_matches, require_target
from halcyon.modules.transport import Result, Transport


def make_dt(extra_child: str | None = None, compat_str: bytes = b"wlan-pcie,bcm4355") -> bytes:
    root = devicetree.DTNode({"name": b"device-tree\0"})
    arm = devicetree.DTNode({"name": b"arm-io\0"})
    arm.children.append(devicetree.DTNode({"name": b"wlan\0", "compatible": compat_str + b"\0"}))
    root.children.append(arm)
    if extra_child:
        root.children.append(devicetree.DTNode({"name": extra_child.encode() + b"\0"}))
    return devicetree.serialize(root)


def make_ipsw(path, version, product, board, cpid, dt: bytes, kernel_payload: bytes = b"\0Darwin Kernel Version 21.6.0: test\0"):
    manifest = {
        "ProductVersion": version, "ProductBuildVersion": "TEST",
        "SupportedProductTypes": [product],
        "BuildIdentities": [{
            "ApChipID": hex(cpid), "ApBoardID": "0x0A",
            "Info": {"DeviceClass": board, "Variant": "Customer Erase Install (IPSW)"},
            "Manifest": {
                "KernelCache": {"Info": {"Path": "kernelcache.release.test"}},
                "DeviceTree": {"Info": {"Path": f"Firmware/all_flash/DeviceTree.{board}.im4p"}},
                "SEP": {"Info": {"Path": f"Firmware/all_flash/sep-firmware.{board}.RELEASE.im4p"}},
            },
        }],
    }
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("BuildManifest.plist", plistlib.dumps(manifest))
        z.writestr("kernelcache.release.test", img4.build_im4p("krnl", "KernelCache", kernel_payload))
        z.writestr(f"Firmware/all_flash/DeviceTree.{board}.im4p", img4.build_im4p("dtre", "DeviceTree", dt))
        z.writestr(f"Firmware/all_flash/sep-firmware.{board}.RELEASE.im4p", img4.build_im4p("sepi", "sepos", b"x" * 300))
    return path


@pytest.fixture
def ipsws(tmp_path):
    t = make_ipsw(tmp_path / "t.ipsw", "15.8.3", "iPhone9,2", "d11ap", 0x8010, make_dt())
    d = make_ipsw(tmp_path / "d.ipsw", "16.7.10", "iPad7,11", "j171ap", 0x8010,
                  make_dt("aop", b"wlan-pcie,bcm4355c0"), b"\0Darwin Kernel Version 22.6.0: test\0")
    return t, d


def test_im4p_roundtrip():
    payload = b"complzss" + b"\0" * 400
    im = img4.parse_im4p(img4.build_im4p("krnl", "KernelCache", payload))
    assert (im.fourcc, im.description, im.payload_kind) == ("krnl", "KernelCache", "lzss")


def test_devicetree_roundtrip_and_diff():
    a, b = devicetree.parse(make_dt()), devicetree.parse(make_dt("aop", b"x"))
    assert devicetree.serialize(a) == make_dt()
    d = devicetree.diff(a, b)
    assert d.only_b == ["device-tree/aop"]
    assert d.compatible_changed[0][0] == "device-tree/arm-io/wlan"


def test_compat(ipsws):
    t, d = ipsws
    with IPSW(t) as ti, IPSW(d) as di:
        rep = compat.analyze(ti, di, "d11ap", "j171ap")
    assert "21.6.0" in rep.xnu_target and "22.6.0" in rep.xnu_donor
    assert rep.dt_diff.only_b == ["device-tree/aop"]
    assert "| KernelCache |" in rep.to_markdown()


def fake_transport(irec: str = "", info: str = "", udid: str = ""):
    def run(argv, timeout):
        return {"idevice_id": Result(0, udid, ""), "ideviceinfo": Result(0 if info else 1, info, ""),
                "irecovery": Result(0 if irec else 1, irec, "")}[argv[0]]
    return Transport(run)


def test_detect_dfu_target():
    st = detect(fake_transport(irec="CPID: 0x8010\nBDID: 0x0a\nECID: 0x1234\nMODE: DFU\nPRODUCT: iPhone9,2\nMODEL: d11ap\n"))
    assert st.mode == "dfu" and st.is_target and st.spec.board_config == "d11ap"


def test_detect_wrong_device_refused():
    st = detect(fake_transport(udid="abc\n", info="ProductType: iPhone10,2\nHardwareModel: D21AP\nProductVersion: 16.7\n"))
    assert st.mode == "normal" and not st.is_target
    with pytest.raises(SafetyError):
        require_target(st)


def test_ipsw_mismatch_refused(ipsws):
    st = detect(fake_transport(irec="CPID: 0x8010\nBDID: 0x0a\nMODE: Recovery\nPRODUCT: iPhone9,2\n"))
    with IPSW(ipsws[1]) as donor, pytest.raises(SafetyError):
        require_ipsw_matches(st, donor)
    with IPSW(ipsws[0]) as ok:
        require_ipsw_matches(st, ok)


def test_guard():
    assert Guard().require_write("x") is False
    with pytest.raises(SafetyError):
        Guard(dry_run=False).require_write("x")
    assert Guard(dry_run=False, confirmed=True).require_write("x")


def test_bootmon():
    log = ["iBoot for d11, Copyright", "Darwin Kernel Version 22.6.0", "AppleSEPManager: boot failed",
           "panic(cpu 0 caller 0xfffffff0): SEP Panic", "launchd[1]: never"]
    s = bootmon.analyze(log)
    assert s.counts["sep"] == 1
    assert s.first_fatal.category == "sep-panic"
    assert s.furthest_stage == "launchd"
    s2 = bootmon.analyze(["Darwin Kernel Version 22", "panic(cpu 1 caller 0x1): Kernel data abort"])
    assert s2.first_fatal.category == "panic" and "FAIL" in s2.verdict()


def test_panic_ips(tmp_path):
    header = '{"bug_type":"210","os_version":"iPhone OS 16.7.10 (20H392)"}'
    body = ('{"build":"20H392","product":"iPhone9,2","kernel":"Darwin Kernel Version 22.6.0",'
            '"panicString":"panic(cpu 0 caller 0x1): Still waiting for root device\\nAppleSEPManager timeout"}')
    f = tmp_path / "panic-full.ips"
    f.write_text(header + "\n" + body)
    pan = panic.parse(f)
    assert pan.product == "iPhone9,2" and pan.build == "20H392"
    assert "rootdev" in pan.categories and "likely" in pan.verdict


def test_panic_text(tmp_path):
    f = tmp_path / "panic.txt"
    f.write_text("Darwin Kernel Version 22.6.0\npanic(cpu 1 caller 0x2): Kernel data abort\n")
    pan = panic.parse(f)
    assert pan.kernel_version.startswith("Darwin") and "panic" in pan.verdict


def test_build_profile(ipsws, tmp_path):
    t, d = ipsws
    prof = tmp_path / "p.toml"
    prof.write_text(f'''name="t"\ntarget="iPhone9,2"\n
[inputs.base]\npath="{t}"\nversion="15.8.3"\n[inputs.donor]\npath="{d}"\n
[[steps]]\nrun="verify-inputs"\n
[[steps]]\nrun="extract"\ninput="base"\nboard="d11ap"\ncomponents=["DeviceTree"]\n
[[steps]]\nrun="extract"\ninput="donor"\nboard="j171ap"\ncomponents=["DeviceTree"]\n
[[steps]]\nrun="dt-diff"\na="base:DeviceTree"\nb="donor:DeviceTree"\n
[[steps]]\nrun="kernel-patch"\n''')
    assert cli.main(["--home", str(tmp_path / "h"), "build", str(prof), "--workdir", str(tmp_path / "w")]) == 0
    rc = cli.main(["--home", str(tmp_path / "h"), "build", str(prof), "--workdir", str(tmp_path / "w2"), "--no-dry-run"])
    assert rc == 4  # stops at the unimplemented kernel-patch step
    assert (tmp_path / "w2/reports/dt-diff.json").exists()


def test_cli_smoke(ipsws, tmp_path, capsys):
    h = ["--home", str(tmp_path / "h")]
    assert cli.main(h + ["targets"]) == 0
    assert cli.main(h + ["ipsw", str(ipsws[0]), "-c", "--verify"]) == 0
    assert cli.main(h + ["compat", str(ipsws[0]), str(ipsws[1]), "--donor-board", "j171ap"]) == 0
    assert cli.main(h + ["sep", str(ipsws[0])]) == 0
    assert cli.main(h + ["hw", "probe-script"]) == 0
    assert "AppleCLCD" in capsys.readouterr().out
