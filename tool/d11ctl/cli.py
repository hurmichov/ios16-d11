"""Точка входа d11ctl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from d11ctl import __version__
from d11ctl.core import log
from d11ctl.core.config import DONOR_PRODUCTS, TARGET_PRODUCTS, default_paths
from d11ctl.core.safety import Context, SafetyError, verify_target

_log = log.get("cli")


def _out(obj, as_json: bool) -> None:
    if as_json or not isinstance(obj, (str, list)):
        print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
    elif isinstance(obj, list):
        print("\n".join(map(str, obj)))
    else:
        print(obj)


# --- команды ----------------------------------------------------------------

def cmd_env(a, ctx):
    from d11ctl.modules import env
    if a.action == "install":
        env.install(ctx.dry_run, with_dev=not a.no_dev)
        return 0
    r = env.check()
    if a.json:
        _out(r, True)
    else:
        print(f"ОС: {r['os']}{'' if r['is_fedora'] else '  (не Fedora!)'}   Python {r['python']}")
        for b, t in r["tools"].items():
            flag = "✔" if t["found"] else ("✘" if t["required"] else "·")
            print(f"  {flag} {b:<20} {t['why']}")
        if r["missing_packages"]:
            print("\nУстановить:  sudo dnf install " + " ".join(r["missing_packages"]))
            print("или:         d11ctl --execute env install")
        if not r["udev_rules"]:
            print("⚠ не найдены udev-правила usbmuxd/libirecovery — без них нужен root")
    return 0 if r["ok"] else 1


def cmd_device(a, ctx):
    from d11ctl.modules import device, usb
    if a.action == "usb":
        _out([f"{d.bus_path}  pid=0x{d.pid:04x}  {d.mode:<9} {d.serial}" for d in usb.enumerate_apple()]
             or ["Apple-устройств на шине нет"], a.json)
        return 0
    devs = device.detect()
    if not devs:
        print("устройство не найдено")
        return 1
    for d in devs:
        info = d.as_dict()
        try:
            verify_target(d)
            info["target_check"] = "OK — iPhone 7 Plus"
        except SafetyError as e:
            info["target_check"] = f"НЕ ЦЕЛЕВОЕ: {e}"
        _out(info, True)
    return 0


def cmd_fw(a, ctx):
    from d11ctl.modules import firmware
    if a.action == "list":
        for f in firmware.list_firmwares(a.product):
            print(f"{'S' if f.signed else ' '} {f.version:<10} {f.build:<10} {f.filename}")
        return 0
    if a.action == "download":
        fw = firmware.find(a.product, a.version)
        if ctx.dry_run:
            print(f"[dry-run] скачал бы {fw.filename} ({(fw.size or 0) >> 20} МБ) в {ctx.paths.cache}")
            print("добавь --execute для загрузки")
            return 0
        print(firmware.download(fw, ctx.paths.cache))
        return 0
    if a.action == "info":
        _out(firmware.summary(Path(a.ipsw)), True)
        return 0
    if a.action == "extract":
        got = firmware.extract(Path(a.ipsw), a.board, a.components,
                               Path(a.out) if a.out else ctx.paths.work / "extract" / a.board)
        _out({k: str(v) for k, v in got.items()}, True)
        return 0
    return 2


def cmd_compat(a, ctx):
    from d11ctl.modules import compat
    kd = dt = None
    if a.base_kc and a.donor_kc:
        kd = compat.diff_kexts(compat.load_kexts(Path(a.base_kc)), compat.load_kexts(Path(a.donor_kc)))
    if a.base_dt and a.donor_dt:
        dt = compat.diff_dt(compat.load_dt(Path(a.base_dt)), compat.load_dt(Path(a.donor_dt)))
    if not (kd or dt):
        print("укажи пару --base-kc/--donor-kc и/или --base-dt/--donor-dt")
        return 2
    if a.json:
        _out({"kexts": kd.as_dict() if kd else None, "devicetree": dt}, True)
    else:
        md = compat.render_markdown(kd, dt, a.base_label, a.donor_label)
        if a.report:
            Path(a.report).write_text(md, encoding="utf-8")
            print(f"отчёт: {a.report}")
        else:
            print(md)
    return 0


def cmd_build(a, ctx):
    from d11ctl.modules import build
    recipe = build.Recipe.load(Path(a.recipe))
    if a.action == "plan":
        for r in build.plan(recipe, ctx.paths.work / recipe.name):
            miss = f"  (нет входов: {', '.join(r['missing_inputs'])})" if r["missing_inputs"] else ""
            print(f"[{r['kind']:<8}] {r['id']:<16} {r['desc']}{miss}")
        return 0
    print(build.execute(ctx, recipe, a.only))
    return 0


def cmd_boot(a, ctx):
    from d11ctl.modules import bootmon
    if a.action == "analyze":
        _out(bootmon.analyze_file(Path(a.file)), True)
        return 0
    out = ctx.paths.logs / f"boot-{log.session_id()}.log"
    res = bootmon.monitor(a.port, out, a.baud, a.duration)
    _out(res, True)
    return 0


def cmd_sep(a, ctx):
    from d11ctl.modules import sep
    base = sep.inspect(Path(a.base_ipsw), a.base_board)
    if a.donor_ipsw:
        donor = sep.inspect(Path(a.donor_ipsw), a.donor_board)
        _out({"base": base, "donor": donor, "notes": sep.compare(base, donor)}, True)
    else:
        _out(base, True)
    return 0


def cmd_diag(a, ctx):
    from d11ctl.modules import device, hwdiag
    dev = device.require_single()
    if dev.mode != "normal":
        print("диагностика периферии работает только в Normal-режиме")
        return 1
    _out(hwdiag.run_all(), True)
    return 0


def cmd_logs(a, ctx):
    from d11ctl.modules import logs
    if a.action == "list":
        _out([str(p) for p in logs.sessions(ctx.paths.logs)] or ["журналов пока нет"], False)
    elif a.action == "show":
        path = Path(a.file) if a.file else (logs.sessions(ctx.paths.logs) or [None])[-1]
        if not path:
            print("журналов пока нет")
            return 1
        for e in logs.tail(path, a.n, a.level):
            print(f"{e['ts']:.3f} {e['level']:<7} {e['module']}: {e['msg']}")
    elif a.action == "analyze":
        _out(logs.analyze(Path(a.file)), True)
    return 0


def cmd_recovery(a, ctx):
    from d11ctl.modules import device, recovery
    dev = device.require_single()
    if a.action == "backup":
        verify_target(dev)
        p = recovery.backup(ctx, dev)
        print(p or "[dry-run] бэкап не выполнялся — добавь --execute")
    elif a.action == "signed":
        fw = recovery.signed_base(dev.product_type or "iPhone9,2")
        print(f"подписана iOS {fw.version} ({fw.build})")
    elif a.action == "restore":
        recovery.restore(ctx, dev, Path(a.ipsw) if a.ipsw else None, erase=a.erase)
    return 0


# --- парсер -----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="d11ctl",
        description="Порт iOS 16 на iPhone 7 Plus (D11/D111, T8010): сборка, диагностика, восстановление.",
        epilog="По умолчанию всё работает в режиме dry-run. Реальные изменения — только с --execute.")
    p.add_argument("--version", action="version", version=f"d11ctl {__version__}")
    p.add_argument("--execute", action="store_true", help="выключить dry-run (разрешить запись)")
    p.add_argument("--yes", action="store_true", help="не спрашивать подтверждение (опасно)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--json", action="store_true", help="машиночитаемый вывод")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("env", help="EVT0: проверка и установка зависимостей Fedora")
    s.add_argument("action", choices=["check", "install"], nargs="?", default="check")
    s.add_argument("--no-dev", action="store_true", help="без -devel пакетов")
    s.set_defaults(fn=cmd_env)

    s = sub.add_parser("device", help="Device Manager / USB Transport")
    s.add_argument("action", choices=["info", "usb"], nargs="?", default="info")
    s.set_defaults(fn=cmd_device)

    s = sub.add_parser("fw", help="Firmware Manager")
    fs = s.add_subparsers(dest="action", required=True)
    x = fs.add_parser("list"); x.add_argument("product", help=f"напр. {', '.join({**TARGET_PRODUCTS, **DONOR_PRODUCTS})}")
    x = fs.add_parser("download"); x.add_argument("product"); x.add_argument("version")
    x = fs.add_parser("info"); x.add_argument("ipsw")
    x = fs.add_parser("extract"); x.add_argument("ipsw"); x.add_argument("board")
    x.add_argument("components", nargs="+", help="KernelCache DeviceTree SEP RestoreSEP ...")
    x.add_argument("-o", "--out")
    s.set_defaults(fn=cmd_fw)

    s = sub.add_parser("compat", help="Compatibility Analyzer")
    s.add_argument("--base-kc"); s.add_argument("--donor-kc")
    s.add_argument("--base-dt"); s.add_argument("--donor-dt")
    s.add_argument("--base-label", default="iOS 15 / D11")
    s.add_argument("--donor-label", default="iPadOS 16.6.1 / J172")
    s.add_argument("--report", help="сохранить Markdown-отчёт")
    s.set_defaults(fn=cmd_compat)

    s = sub.add_parser("build", help="Build Engine")
    s.add_argument("action", choices=["plan", "run"])
    s.add_argument("recipe")
    s.add_argument("--only", nargs="*")
    s.set_defaults(fn=cmd_build)

    s = sub.add_parser("boot", help="Boot Monitor")
    bs = s.add_subparsers(dest="action", required=True)
    x = bs.add_parser("monitor"); x.add_argument("port", help="/dev/ttyACM0 (адаптер RP2350)")
    x.add_argument("--baud", type=int, default=115200); x.add_argument("--duration", type=float)
    x = bs.add_parser("analyze"); x.add_argument("file")
    s.set_defaults(fn=cmd_boot)

    s = sub.add_parser("sep", help="SEP Compatibility")
    s.add_argument("base_ipsw"); s.add_argument("--base-board", default="d11ap")
    s.add_argument("--donor-ipsw"); s.add_argument("--donor-board", default="j172ap")
    s.set_defaults(fn=cmd_sep)

    s = sub.add_parser("diag", help="Hardware Diagnostics")
    s.set_defaults(fn=cmd_diag)

    s = sub.add_parser("logs", help="Log Manager")
    s.add_argument("action", choices=["list", "show", "analyze"])
    s.add_argument("file", nargs="?"); s.add_argument("-n", type=int, default=50)
    s.add_argument("--level")
    s.set_defaults(fn=cmd_logs)

    s = sub.add_parser("recovery", help="Recovery Manager")
    s.add_argument("action", choices=["backup", "signed", "restore"])
    s.add_argument("--ipsw"); s.add_argument("--erase", action="store_true")
    s.set_defaults(fn=cmd_recovery)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    paths = default_paths().ensure()
    logfile = log.setup(paths.logs, a.verbose)
    ctx = Context(paths=paths, dry_run=not a.execute, assume_yes=a.yes)
    _log.debug("старт", extra={"data": {"argv": sys.argv, "dry_run": ctx.dry_run, "log": str(logfile)}})
    try:
        return a.fn(a, ctx)
    except SafetyError as e:
        _log.error("ОСТАНОВЛЕНО ЗАЩИТОЙ: %s", e)
        return 3
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        sys.stderr.close()
        return 0
    except Exception as e:  # noqa: BLE001
        _log.error("%s", e)
        _log.debug("трассировка", exc_info=True)
        return 1
