"""Build Engine: reproducible, profile-driven pipeline.

A profile (profiles/*.toml) declares the inputs (IPSWs with expected SHA-256) and an
ordered list of steps. Each step writes into a content-addressed work directory and
records its inputs/outputs in build-manifest.json, so a build can be reproduced or
resumed. Steps that are not yet implemented fail loudly instead of pretending.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from halcyon.modules import devicetree, img4, kernelcache
from halcyon.modules.firmware import IPSW, sha256_file
from halcyon.modules.logs import Session


class StepNotImplemented(RuntimeError):
    pass


@dataclass
class Context:
    profile: dict
    workdir: Path
    session: Session
    dry_run: bool
    inputs: dict[str, Path] = field(default_factory=dict)
    artifacts: dict[str, Path] = field(default_factory=dict)
    record: list[dict] = field(default_factory=list)


StepFn = Callable[[Context, dict], dict]
STEPS: dict[str, StepFn] = {}


def step(name: str):
    def deco(fn: StepFn) -> StepFn:
        STEPS[name] = fn
        return fn
    return deco


def load_profile(path: Path) -> dict:
    with open(path, "rb") as f:
        prof = tomllib.load(f)
    for key in ("name", "target", "inputs", "steps"):
        if key not in prof:
            raise ValueError(f"profile {path}: missing [{key}]")
    return prof


# ---------------------------------------------------------------- steps

@step("verify-inputs")
def _verify_inputs(ctx: Context, args: dict) -> dict:
    out = {}
    for name, spec in ctx.profile["inputs"].items():
        p = Path(spec["path"]).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"input {name}: {p} not found (download it yourself from Apple)")
        want = spec.get("sha256")
        got = sha256_file(p) if want or not ctx.dry_run else None
        if want and got != want.lower():
            raise ValueError(f"input {name}: sha256 mismatch\n  want {want}\n  got  {got}")
        with IPSW(p) as ip:
            if spec.get("version") and ip.product_version != spec["version"]:
                raise ValueError(f"input {name}: expected {spec['version']}, IPSW is {ip.product_version}")
            out[name] = {"version": ip.product_version, "build": ip.build, "sha256": got}
        ctx.inputs[name] = p
    return out


@step("extract")
def _extract(ctx: Context, args: dict) -> dict:
    """args: input=<name>, board=<boardconfig>, components=[...]"""
    src = ctx.inputs[args["input"]]
    dest = ctx.workdir / "extract" / args["input"]
    got = {}
    with IPSW(src) as ip:
        ident = next(iter(ip.identities_for(args["board"])), None)
        if ident is None:
            raise ValueError(f"{src.name}: no identity for {args['board']}")
        for comp in args["components"]:
            inner = ident.components.get(comp)
            if not inner:
                raise KeyError(f"{src.name}/{args['board']}: no component {comp}")
            if ctx.dry_run:
                got[comp] = inner
                continue
            p = ip.extract(inner, dest)
            ctx.artifacts[f"{args['input']}:{comp}"] = p
            got[comp] = {"path": str(p.relative_to(ctx.workdir)), "sha256": sha256_file(p)}
    return got


@step("dt-diff")
def _dt_diff(ctx: Context, args: dict) -> dict:
    """args: a=<input:DeviceTree>, b=<input:DeviceTree> — writes a diff report."""
    if ctx.dry_run:
        return {"planned": True}
    trees = []
    for k in (args["a"], args["b"]):
        im = img4.parse_im4p(ctx.artifacts[k].read_bytes())
        trees.append(devicetree.parse(im.payload))
    d = devicetree.diff(*trees)
    rep = ctx.workdir / "reports" / "dt-diff.json"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps({"only_a": d.only_a, "only_b": d.only_b,
                               "compatible_changed": d.compatible_changed}, indent=1))
    return {"report": str(rep.relative_to(ctx.workdir)), "only_a": len(d.only_a), "only_b": len(d.only_b)}


@step("kext-diff")
def _kext_diff(ctx: Context, args: dict) -> dict:
    """args: a=<input:KernelCache>, b=<input:KernelCache> — writes a kext inventory diff."""
    if ctx.dry_run:
        return {"planned": True}
    ka = kernelcache.parse(ctx.artifacts[args["a"]].read_bytes(), args["a"])
    kb = kernelcache.parse(ctx.artifacts[args["b"]].read_bytes(), args["b"])
    d = kernelcache.diff(ka, kb)
    rep = ctx.workdir / "reports" / "kext-diff.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(d.to_markdown())
    return {"report": str(rep.relative_to(ctx.workdir)), "only_a": len(d.only_a),
            "only_b": len(d.only_b), "common": len(d.common)}


def _todo(name: str, stage: str) -> StepFn:
    def fn(ctx: Context, args: dict) -> dict:
        if ctx.dry_run:
            return {"planned": True, "status": f"not implemented ({stage})"}
        raise StepNotImplemented(f"step '{name}' is planned for {stage} and not implemented yet")
    return fn


for _n, _s in (("kernel-patch", "EVT2"), ("kext-relink", "EVT2"), ("dt-merge", "EVT2"),
               ("trustcache", "EVT2"), ("ramdisk", "EVT2"), ("rootfs-assemble", "EVT2/EVT4"),
               ("bootchain", "EVT3")):
    STEPS[_n] = _todo(_n, _s)


# ---------------------------------------------------------------- runner

def run(profile_path: Path, workdir: Path, session: Session, dry_run: bool = True,
        only: list[str] | None = None) -> Context:
    prof = load_profile(profile_path)
    workdir.mkdir(parents=True, exist_ok=True)
    ctx = Context(prof, workdir, session, dry_run)
    session.event("build.start", profile=prof["name"], workdir=str(workdir), dry_run=dry_run)
    for i, st in enumerate(prof["steps"]):
        name = st["run"]
        if only and name not in only and name != "verify-inputs":
            continue
        fn = STEPS.get(name)
        if fn is None:
            raise KeyError(f"unknown step {name!r}; known: {sorted(STEPS)}")
        args = {k: v for k, v in st.items() if k != "run"}
        session.event("build.step", n=i, step=name, args=args)
        result = fn(ctx, args)
        ctx.record.append({"n": i, "step": name, "args": args, "result": result})
        session.event("build.step.done", n=i, step=name, result=result)
    if not dry_run:
        (workdir / "build-manifest.json").write_text(json.dumps(
            {"profile": prof["name"], "profile_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
             "steps": ctx.record}, indent=1, default=str))
    session.event("build.end")
    return ctx
