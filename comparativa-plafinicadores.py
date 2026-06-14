
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON = sys.executable
DOMAIN = ROOT / "pddl" / "blocks" / "domain.pddl"
INSTANCES = [1, 10, 20]


def parse_last(pattern: str, text: str, cast):
    matches = re.findall(pattern, text)
    return cast(matches[-1]) if matches else None


def run_pyperplan(instance: int) -> dict:
    problem = ROOT / "pddl" / "blocks" / f"instance-{instance}.pddl"
    cmd = [
        PYTHON,
        "-m",
        "pyperplan",
        "-l",
        "info",
        "-s",
        "gbf",
        "-H",
        "hff",
        str(DOMAIN),
        str(problem),
    ]

    started = time.perf_counter()
    completed = subprocess.run(
        cmd,
        env={**os.environ, "PYTHONPATH": str(ROOT / ".codex_deps")},
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    elapsed = time.perf_counter() - started
    output = completed.stdout + completed.stderr

    plan_length = parse_last(r"Plan length: (\d+)", output, int)
    return {
        "instancia": f"instance-{instance}",
        "planificador": "Pyperplan",
        "configuracion": "GBFS + hFF",
        "busqueda": "greedy best-first search",
        "heuristica": "hFF",
        "ok": completed.returncode == 0 and plan_length is not None,
        "nodos_expandidos": parse_last(r"(\d+) Nodes expanded", output, int),
        "nodos_generados": None,
        "tiempo_busqueda_s": parse_last(r"Search time: ([0-9.]+)", output, float),
        "tiempo_total_s": round(elapsed, 4),
        "longitud_plan": plan_length,
        "coste_plan": plan_length,
    }


def run_fast_downward(instance: int, alias: str, config: str, heuristic: str) -> dict:
    problem = ROOT / "pddl" / "blocks" / f"instance-{instance}.pddl"
    planner = ROOT / ".codex_deps" / "up_fast_downward" / "downward" / "fast-downward.py"
    plan_file = ROOT / "pddl" / "blocks" / f"fd-{alias}-instance-{instance}.plan"
    cmd = [
        PYTHON,
        str(planner),
        "--overall-time-limit",
        "60",
        "--plan-file",
        str(plan_file),
        "--alias",
        alias,
        str(DOMAIN),
        str(problem),
    ]

    started = time.perf_counter()
    completed = subprocess.run(
        cmd,
        env={**os.environ, "PYTHONPATH": str(ROOT / ".codex_deps")},
        capture_output=True,
        text=True,
        timeout=75,
        check=False,
    )
    elapsed = time.perf_counter() - started
    output = completed.stdout + completed.stderr
    found = "Solution found." in output or plan_file.exists()
    plan_cost = parse_last(r"Plan cost: (\d+)", output, int)

    return {
        "instancia": f"instance-{instance}",
        "planificador": "Fast Downward",
        "configuracion": config,
        "busqueda": alias,
        "heuristica": heuristic,
        "ok": found,
        "nodos_expandidos": parse_last(r"Expanded (\d+) state", output, int),
        "nodos_generados": parse_last(r"Generated (\d+) state", output, int),
        "estados_evaluados": parse_last(r"Evaluated (\d+) state", output, int),
        "tiempo_busqueda_s": parse_last(r"Search time: ([0-9.]+)s", output, float),
        "tiempo_total_s": round(elapsed, 4),
        "longitud_plan": plan_cost,
        "coste_plan": plan_cost,
    }


def block_count(instance_name: str) -> int:
    text = (ROOT / "pddl" / "blocks" / f"{instance_name}.pddl").read_text()
    match = re.search(r":objects(.*?)\-\s*block", text, re.S | re.I)
    return len(match.group(1).split()) if match else 0


def write_chart(results: list[dict]) -> None:
    import matplotlib.pyplot as plt

    labels = [f"instance-{i}" for i in INSTANCES]
    configs = []
    for row in results:
        name = f"{row['planificador']}\n{row['configuracion']}"
        if name not in configs:
            configs.append(name)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), dpi=180)
    colors = ["#2f6f73", "#9c5f2a", "#4f5d95"]
    x_labels = [f"{label}\n({block_count(label)} bloques)" for label in labels]

    for index, config in enumerate(configs):
        expanded = []
        costs = []
        for label in labels:
            row = next(
                item
                for item in results
                if item["instancia"] == label
                and f"{item['planificador']}\n{item['configuracion']}" == config
            )
            expanded.append(row.get("nodos_expandidos") or 0)
            costs.append(row.get("longitud_plan") or 0)
        axes[0].plot(x_labels, expanded, marker="o", color=colors[index], label=config.replace("\n", " "))
        axes[1].plot(x_labels, costs, marker="o", color=colors[index], label=config.replace("\n", " "))

    axes[0].set_yscale("log")
    axes[0].set_title("Estados expandidos (escala log)")
    axes[0].set_ylabel("Estados")
    axes[1].set_title("Longitud/coste del plan")
    axes[1].set_ylabel("Acciones")
    for axis in axes:
        axis.grid(True, alpha=0.25)
        axis.set_xlabel("Instancia")
    axes[1].legend(fontsize=7, loc="upper left")
    fig.tight_layout()
    fig.savefig(ROOT / "comparativa_planificadores.png", bbox_inches="tight")


def main() -> None:
    results = []
    for instance in INSTANCES:
        results.append(run_pyperplan(instance))

    fast_downward_configs = [
        ("lama-first", "LAMA-first", "landmarks + heurísticas tipo FF"),
        ("seq-opt-lmcut", "A* + LM-cut", "LM-cut"),
    ]
    for instance in INSTANCES:
        for alias, config, heuristic in fast_downward_configs:
            results.append(run_fast_downward(instance, alias, config, heuristic))

    (ROOT / "resultados_finales.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False)
    )
    write_chart(results)
    print("Resultados escritos en resultados_finales.json")
    print("Gráfica escrita en comparativa_planificadores.png")


if __name__ == "__main__":
    main()
