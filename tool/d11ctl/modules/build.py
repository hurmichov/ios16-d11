"""Build Engine: воспроизводимый конвейер сборки экспериментального образа.

Рецепт — JSON со списком шагов. Каждый шаг объявляет входы и выходы; после выполнения
их SHA-256 записываются в build-lock.json. Повторная сборка из тех же входов обязана дать
те же хеши, иначе сборка помечается невоспроизводимой.

На EVT0 шаги, для которых ещё нет реализации, имеют тип "research" и только
документируют, что должно происходить.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from d11ctl.core import log, runner
from d11ctl.core.safety import Context
from d11ctl.modules import firmware

_log = log.get("build")


@dataclass
class Step:
    id: str
    kind: str  # extract | tool | research
    desc: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    args: dict = field(default_factory=dict)


@dataclass
class Recipe:
    name: str
    base: dict
    donor: dict
    steps: list[Step]

    @classmethod
    def load(cls, path: Path) -> "Recipe":
        d = json.loads(path.read_text())
        return cls(d["name"], d["base"], d["donor"], [Step(**s) for s in d["steps"]])


def _resolve(work: Path, rel: str) -> Path:
    p = (work / rel).resolve()
    if work.resolve() not in p.parents and p != work.resolve():
        raise ValueError(f"путь {rel} выходит за пределы рабочего каталога")
    return p


def plan(recipe: Recipe, work: Path) -> list[dict]:
    produced: set[str] = set()
    rows = []
    for s in recipe.steps:
        missing = [i for i in s.inputs if i not in produced and not _resolve(work, i).exists()
                   and not i.startswith("@")]
        rows.append({"id": s.id, "kind": s.kind, "desc": s.desc,
                     "missing_inputs": missing, "outputs": s.outputs})
        produced.update(s.outputs)
    return rows


def _run_step(ctx: Context, recipe: Recipe, s: Step, work: Path) -> None:
    if s.kind == "research":
        _log.warning("шаг %s пока исследовательский: %s", s.id, s.desc)
        return
    if s.kind == "extract":
        src = recipe.base if s.args.get("from") == "base" else recipe.donor
        ipsw = ctx.paths.cache / s.args["ipsw"]
        if not ipsw.exists():
            raise FileNotFoundError(f"нет {ipsw}: сначала `d11ctl fw download {src['product']} {src['version']}`")
        firmware.extract(ipsw, src["board"], s.args["components"], _resolve(work, s.args.get("dir", ".")))
        return
    if s.kind == "tool":
        argv = [a.replace("{work}", str(work)) for a in s.args["argv"]]
        runner.run(argv, mutating=bool(s.args.get("mutating")), dry_run=ctx.dry_run,
                   timeout=s.args.get("timeout", 600), check=True)
        return
    raise ValueError(f"неизвестный тип шага {s.kind}")


def execute(ctx: Context, recipe: Recipe, only: list[str] | None = None) -> Path:
    work = ctx.paths.work / recipe.name
    work.mkdir(parents=True, exist_ok=True)
    lock = {"recipe": recipe.name, "started": time.strftime("%FT%T"), "steps": {}}
    for s in recipe.steps:
        if only and s.id not in only:
            continue
        _log.info("── шаг %s (%s): %s", s.id, s.kind, s.desc)
        _run_step(ctx, recipe, s, work)
        outs = {}
        for o in s.outputs:
            p = _resolve(work, o)
            if p.is_file():
                outs[o] = firmware.hash_file(p, "sha256")
        lock["steps"][s.id] = {"inputs": s.inputs, "outputs": outs}

    lock_path = work / "build-lock.json"
    if lock_path.exists():
        prev = json.loads(lock_path.read_text())
        for sid, st in lock["steps"].items():
            old = prev.get("steps", {}).get(sid, {}).get("outputs", {})
            for o, h in st["outputs"].items():
                if o in old and old[o] != h:
                    _log.error("НЕВОСПРОИЗВОДИМО: %s/%s изменил хеш", sid, o)
    lock_path.write_text(json.dumps(lock, indent=2, ensure_ascii=False))
    _log.info("build-lock: %s", lock_path)
    return lock_path
