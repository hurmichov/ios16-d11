"""halcyon — command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from halcyon import __version__, devices
from halcyon.modules import bootmon, build, compat, deps, hwdiag, kernelcache, panic, recovery, sep
from halcyon.modules import device as devmod
from halcyon.modules.firmware import IPSW
from halcyon.modules.logs import Session
from halcyon.modules.safety import Guard, SafetyError
from halcyon.modules.transport import Transport


def _guard(a) -> Guard:
    return Guard(dry_run=not a.no_dry_run, confirmed=a.i_understand)


# ------------------------------------------------------------------ commands

def cmd_doctor(a, s: Session) -> int:
    res = deps.check()
    for d, ok in res:
        flag = "ok " if ok else ("MISS" if d.required else "opt ")
        print(f"[{flag}] {d.name:<20} {d.why}")
    s.event("doctor", missing=[d.name for d, ok in res if not ok])
    cmd = deps.dnf_command(res, include_optional=a.all)
    if cmd:
        print(f"\nУстановить:\n  {cmd}")
        return 1 if any(not ok and d.required for d, ok in res) else 0
    print("\nВсе зависимости на месте.")
    return 0


def cmd_device(a, s: Session) -> int:
    st = devmod.detect(Transport())
    s.event("device", mode=st.mode, product=st.product_type, cpid=st.cpid, bdid=st.bdid, ios=st.ios_version)
    if st.mode == "none":
        print("Устройство не найдено (проверь кабель USB-A→Lightning, usbmuxd, режим DFU/Recovery).")
        return 2
    spec = st.spec
    print(f"mode        : {st.mode}")
    print(f"ProductType : {st.product_type}")
    print(f"BoardConfig : {st.board_config}")
    print(f"CPID / BDID : {st.cpid and hex(st.cpid)} / {st.bdid and hex(st.bdid)}")
    print(f"iOS         : {st.ios_version or '-'} ({st.build or '-'})")
    print(f"target      : {'YES — ' + spec.name if spec else 'NO (unsupported device)'}")
    if a.json:
        print(json.dumps(st.raw, indent=1))
    return 0 if spec else 3


def cmd_ipsw_info(a, s: Session) -> int:
    with IPSW(a.ipsw) as ip:
        print(f"{ip.path.name}: iOS {ip.product_version} ({ip.build})")
        print(f"SupportedProductTypes: {', '.join(ip.supported)}")
        for ident in ip.identities:
            cp = f"{ident.cpid:#x}" if ident.cpid else "?"
            print(f"  #{ident.index:<2} {ident.board_config:<8} CPID {cp:<7} {ident.variant}")
            if a.components:
                for k, v in sorted(ident.components.items()):
                    print(f"       {k:<28} {v}")
        if a.verify:
            bad = ip.verify_zip()
            print("integrity: OK" if not bad else f"integrity: BAD {bad}")
            s.event("ipsw.verify", ipsw=str(ip.path), bad=bad)
            return 1 if bad else 0
    return 0


def cmd_compat(a, s: Session) -> int:
    with IPSW(a.target) as t, IPSW(a.donor) as d:
        rep = compat.analyze(t, d, a.target_board, a.donor_board)
    md = rep.to_markdown()
    p = s.attach("compat.md", md)
    if a.out:
        Path(a.out).write_text(md)
    print(md)
    print(f"(saved: {p})", file=sys.stderr)
    return 0


def cmd_build(a, s: Session) -> int:
    dry = not a.no_dry_run
    ctx = build.run(Path(a.profile), Path(a.workdir), s, dry_run=dry, only=a.only)
    for r in ctx.record:
        print(f"[{r['n']:>2}] {r['step']:<16} {json.dumps(r['result'], ensure_ascii=False, default=str)[:140]}")
    if dry:
        print("\n(dry-run: ничего не записано; запусти с --no-dry-run для реального выполнения)")
    return 0


def cmd_boot_monitor(a, s: Session) -> int:
    if a.file:
        lines = open(a.file, encoding="utf-8", errors="replace")
    elif a.serial:
        lines = bootmon.stream_lines(bootmon.open_serial(a.serial, a.baud))
    else:
        lines = sys.stdin
    raw = open(s.dir / "boot.log", "w", encoding="utf-8")

    def tee():
        for line in lines:
            raw.write(line if line.endswith("\n") else line + "\n")
            raw.flush()
            ev = bootmon.classify(line)
            if ev and (a.verbose or ev.severity != "info"):
                print(f"[{ev.stage:<7}] {ev.severity:<5} {ev.category:<11} {ev.line[:200]}")
                s.event("boot", stage=ev.stage, severity=ev.severity, category=ev.category, line=ev.line)
            elif a.raw:
                print(line.rstrip())
            yield line

    try:
        summ = bootmon.analyze(tee())
    except KeyboardInterrupt:
        summ = bootmon.analyze(open(s.dir / "boot.log", encoding="utf-8"))
    print("\n" + summ.verdict())
    print(dict(summ.counts))
    s.event("boot.summary", verdict=summ.verdict(), counts=dict(summ.counts))
    return 1 if summ.first_fatal else 0


def cmd_kernel(a, s: Session) -> int:
    if a.action == "kexts":
        kc = kernelcache.parse_file(a.kc[0])
        print(f"{kc.source}: filetype={'MH_FILESET' if kc.is_fileset else hex(kc.filetype)} "
              f"kexts={len(kc.kexts)}")
        if kc.kernel_version:
            print(kc.kernel_version)
        for k in kc.kexts:
            tag = "[kernel]" if k.is_kernel else "        "
            m = f"  [{', '.join(k.matches)}]" if k.matches else ""
            print(f"{tag} {k.bundle_id:<52} {k.version or '':<12} {k.vmaddr and hex(k.vmaddr) or ''}{m}")
        s.event("kernel.kexts", source=kc.source, count=len(kc.kexts), fileset=kc.is_fileset)
        return 0
    # diff
    ka = kernelcache.parse_file(a.kc[0])
    kb = kernelcache.parse_file(a.kc[1])
    d = kernelcache.diff(ka, kb)
    hw = {c.key: c.name for c in hwdiag.COMPONENTS}
    md = d.to_markdown(hardware_hint=hw)
    s.attach("kext-diff.md", md)
    if a.out:
        Path(a.out).write_text(md)
    print(md)
    s.event("kernel.diff", only_a=len(d.only_a), only_b=len(d.only_b), common=len(d.common))
    return 0


def cmd_panic(a, s: Session) -> int:
    rc = 0
    for path in a.file:
        pan = panic.parse(path)
        print(pan.summary())
        print()
        s.event("panic", source=pan.source, verdict=pan.verdict, categories=pan.categories)
        if pan.categories:
            rc = 1
    return rc


def cmd_sep(a, s: Session) -> int:
    for path in a.ipsw:
        with IPSW(path) as ip:
            for board in {i.board_config for i in ip.identities} if not a.board else [a.board]:
                for info in sep.inspect(ip, board):
                    print(f"{info.ipsw:<22} {info.board:<8} {info.fourcc or '-':<5} "
                          f"{'keybag' if info.encrypted else 'plain' if info.encrypted is False else '-':<7} "
                          f"{info.description or ''} {info.path or ''}")
    print("\nЗамечания:")
    for f in sep.FINDINGS:
        print(f" - {f}")
    return 0


def cmd_hw(a, s: Session) -> int:
    if a.action == "matrix":
        for c in hwdiag.COMPONENTS:
            print(f"{c.key:<9} {c.track:<8} {c.name:<30} {', '.join(c.ioreg_classes)}")
    elif a.action == "probe-script":
        sys.stdout.write(hwdiag.ioreg_probe_script())
    elif a.action == "battery":
        info = hwdiag.battery(Transport())
        print(json.dumps(info, indent=1, ensure_ascii=False) if info else "нет данных (устройство в normal mode?)")
    return 0


def cmd_backup(a, s: Session) -> int:
    argv = recovery.backup(Path(a.dest), _guard(a), s)
    print(" ".join(argv) + ("   (dry-run)" if not a.no_dry_run else ""))
    return 0


def cmd_restore(a, s: Session) -> int:
    argv = recovery.restore_stock(Path(a.ipsw), _guard(a), s, erase=a.erase)
    print(" ".join(argv) + ("   (dry-run)" if not a.no_dry_run else ""))
    return 0


def cmd_targets(a, s: Session) -> int:
    for d in devices.ALL:
        v = " (verify)" if d.verify else ""
        print(f"{d.role:<6} {d.product_type:<11} {d.board_config:<7} {d.cpid:#x} {d.name}{v}")
    return 0


# ------------------------------------------------------------------ parser

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="halcyon", description="iOS 16 port toolkit for iPhone 7 Plus (D11/D111)")
    p.add_argument("--version", action="version", version=f"halcyon {__version__}")
    p.add_argument("--home", help="data/log directory (default ~/.local/share/halcyon)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def writes(sp):
        sp.add_argument("--no-dry-run", action="store_true", help="actually perform writes")
        sp.add_argument("--i-understand", action="store_true", help="confirm destructive operation")

    sp = sub.add_parser("doctor", help="check Fedora dependencies")
    sp.add_argument("--all", action="store_true", help="include optional packages in dnf line")
    sp.set_defaults(fn=cmd_doctor)

    sp = sub.add_parser("device", help="detect connected device and mode")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_device)

    sub.add_parser("targets", help="list target and donor devices").set_defaults(fn=cmd_targets)

    sp = sub.add_parser("ipsw", help="inspect an IPSW")
    sp.add_argument("ipsw")
    sp.add_argument("-c", "--components", action="store_true")
    sp.add_argument("--verify", action="store_true", help="CRC-check all members")
    sp.set_defaults(fn=cmd_ipsw_info)

    sp = sub.add_parser("compat", help="compare target iOS 15 IPSW with an iOS 16 donor")
    sp.add_argument("target")
    sp.add_argument("donor")
    sp.add_argument("--target-board", default="d11ap")
    sp.add_argument("--donor-board")
    sp.add_argument("-o", "--out")
    sp.set_defaults(fn=cmd_compat)

    sp = sub.add_parser("build", help="run a build profile")
    sp.add_argument("profile")
    sp.add_argument("--workdir", default="work")
    sp.add_argument("--only", nargs="*")
    sp.add_argument("--no-dry-run", action="store_true")
    sp.set_defaults(fn=cmd_build)

    sp = sub.add_parser("boot-monitor", help="classify a boot log (serial / file / stdin)")
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--serial", help="e.g. /dev/ttyACM0 (RP2350 adapter)")
    g.add_argument("--file")
    sp.add_argument("--baud", type=int, default=115200)
    sp.add_argument("-v", "--verbose", action="store_true", help="show info milestones too")
    sp.add_argument("--raw", action="store_true", help="echo unclassified lines")
    sp.set_defaults(fn=cmd_boot_monitor)

    sp = sub.add_parser("kernel", help="kernelcache inventory (list kexts / diff two kernelcaches)")
    sp.add_argument("action", choices=["kexts", "diff"])
    sp.add_argument("kc", nargs="+", help="kexts: one kernelcache; diff: A (iOS15/D11) then B (iOS16 donor)")
    sp.add_argument("-o", "--out")
    sp.set_defaults(fn=cmd_kernel)

    sp = sub.add_parser("panic", help="parse & classify an on-disk kernel panic (.ips or text)")
    sp.add_argument("file", nargs="+")
    sp.set_defaults(fn=cmd_panic)

    sp = sub.add_parser("sep", help="SEP firmware research report")
    sp.add_argument("ipsw", nargs="+")
    sp.add_argument("--board")
    sp.set_defaults(fn=cmd_sep)

    sp = sub.add_parser("hw", help="hardware diagnostics")
    sp.add_argument("action", choices=["matrix", "probe-script", "battery"])
    sp.set_defaults(fn=cmd_hw)

    sp = sub.add_parser("backup", help="full user-data backup (idevicebackup2)")
    sp.add_argument("dest")
    writes(sp)
    sp.set_defaults(fn=cmd_backup)

    sp = sub.add_parser("restore", help="restore stock signed iOS 15 (idevicerestore)")
    sp.add_argument("ipsw")
    sp.add_argument("--erase", action="store_true")
    writes(sp)
    sp.set_defaults(fn=cmd_restore)
    return p


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    s = Session(Path(a.home) if a.home else None, a.cmd)
    try:
        return a.fn(a, s)
    except (SafetyError, build.StepNotImplemented, FileNotFoundError, ValueError, KeyError) as e:
        s.event("error", type=type(e).__name__, msg=str(e))
        print(f"halcyon: {e}", file=sys.stderr)
        return 4
    finally:
        s.close()
