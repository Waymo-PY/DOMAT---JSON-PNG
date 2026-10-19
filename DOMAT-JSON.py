# Spouštějte ve VS Code / PowerShell:  python DOMAT-JSONc.py
"""
JSON > PNG

Načte jeden nebo více JSON logů střídače a vytvoří PNG
s teplotou, výstupem, výkonem stringů v kW a seznamem chyb u každé jednotky.

"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Načtení JSON
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    """Převede jeden JSON log na slovník pro kreslení grafů."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    times = [datetime.strptime(r["timestamp"], "%Y-%m-%dT%H:%M:%SZ") for r in rows]
    string_names = list((rows[0].get("strings") or {}).keys())

    errors = []
    for i, row in enumerate(rows):
        for err in row.get("instructionErrors") or []:
            errors.append((times[i], err.get("errorMessage", "")))

    return {
        "file": path.name,
        "times": times,
        "temp": [row["inverterTemperature"] for row in rows],
        "outflow": [1 if row.get("outflowEnabled") else 0 for row in rows],
        "strings": {
            name: [row.get("strings", {}).get(name) for row in rows]
            for name in string_names
        },
        "errors": errors,
        "error_idx": [i for i, row in enumerate(rows) if row.get("instructionErrors")],
    }


# ---------------------------------------------------------------------------
# Pomocné funkce grafů
# ---------------------------------------------------------------------------

def mark_errors(ax, ds: dict) -> None:
    """Vykreslí červenou čáru v čase každého erroru."""
    for i in ds["error_idx"]:
        ax.axvline(ds["times"][i], color="red", linestyle="--", linewidth=1, alpha=0.7)


def format_time_axis(ax, times: list[datetime]) -> None:
    """Popisky času"""
    ax.set_xlim(times[0], times[-1])
    ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=range(0, 60, 5)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_minor_locator(mdates.MinuteLocator(interval=1))
    ax.grid(True, which="major", alpha=0.3)
    ax.grid(True, which="minor", alpha=0.12)
    ax.tick_params(axis="x", which="major", labelsize=8, labelbottom=True, rotation=0)
    ax.tick_params(axis="x", which="minor", length=3)


# ---------------------------------------------------------------------------
# Jeden sloupec střídače  (teplota / výstup / výkon / chyby)
# ---------------------------------------------------------------------------

def plot_column(axes, ds: dict, title: str) -> None:
    ax_temp, ax_out, ax_mpp, ax_err = axes
    t = ds["times"]

    # Teplota
    ax_temp.plot(t, ds["temp"], color="C3", marker="o", markersize=3)
    mark_errors(ax_temp, ds)
    ax_temp.set_title(title)
    ax_temp.set_ylabel("Temp [°C]")
    format_time_axis(ax_temp, t)

    # Výstup  (true / false)
    ax_out.step(t, ds["outflow"], where="post", color="C2")
    mark_errors(ax_out, ds)
    ax_out.set_yticks([0, 1], ["false", "true"])
    ax_out.set_ylabel("Outflow")
    ax_out.set_ylim(-0.1, 1.2)
    format_time_axis(ax_out, t)

    # Výkon MPP (kW)
    for name, values in ds["strings"].items():
        ax_mpp.plot(t, values, marker="o", markersize=3, label=name)
    mark_errors(ax_mpp, ds)
    ax_mpp.set_ylabel("Power [kW]")
    ax_mpp.set_ylim(0, 3)
    ax_mpp.set_xlabel("Time (UTC)")
    ax_mpp.legend(loc="best", fontsize=8)
    format_time_axis(ax_mpp, t)

    # Seznam chyb jen pro jeden střídač
    ax_err.axis("off")
    ax_err.set_title("Errors", loc="left", fontsize=10)
    text = (
        "\n".join(f"{ts:%H:%M:%S}  {msg}" for ts, msg in ds["errors"])
        if ds["errors"]
        else "No errors."
    )
    ax_err.text(
        0.01,
        0.95,
        text,
        va="top",
        ha="left",
        family="monospace",
        fontsize=8,
        transform=ax_err.transAxes,
    )


# ---------------------------------------------------------------------------
# Výsledné PNG
# ---------------------------------------------------------------------------

def build_figure(datasets: list[dict]) -> plt.Figure:
    n = len(datasets)
    fig, axes = plt.subplots(
        4,
        n,
        figsize=(6.8 * n, 10.2),
        gridspec_kw={"height_ratios": [2, 1.3, 2, 1.1]},
        squeeze=False,
    )

    for col, ds in enumerate(datasets, start=1):
        plot_column(
            [axes[0][col - 1], axes[1][col - 1], axes[2][col - 1], axes[3][col - 1]],
            ds,
            title=f"Invertor_{col:02d}",
        )

    fig.suptitle("JSON>PNG - Invertors", fontsize=13)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Čitelnost Terminálu VS code / Windows
# ---------------------------------------------------------------------------

RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"


def fail(message: str) -> None:
    """Vypíše chybu červeně"""
    print(f"{RED}{message}{RESET}", file=sys.stderr)
    raise SystemExit(1)


def ok(message: str) -> None:
    """Vypíše uložení grafu zeleně."""
    print(f"{GREEN}{message}{RESET}")


def main() -> None:
    parser = argparse.ArgumentParser(description="JSON > PNG dashboard střídačů")
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="JSON soubory (výchozí: dataset_*.json vedle tohoto skriptu)",
    )
    parser.add_argument("-o", "--output", type=Path, default=Path("Graphs.png"))
    parser.add_argument("--show", action="store_true", help="Otevřít náhledové okno")
    args = parser.parse_args()

    folder = Path(__file__).resolve().parent
    if args.files:
        missing = [str(f) for f in args.files if not Path(f).exists()]
        if missing:
            fail("Error: JSON file(s) not found:\n  " + "\n  ".join(missing))
        paths = args.files
    else:
        paths = sorted(folder.glob("dataset_*.json"))
        if not paths:
            fail(
                "Error: no JSON files ready to convert.\n"
                f"  Looked for dataset_*.json in: {folder}\n"
                "  Place inverter logs in that folder, or pass the file paths."
            )

    datasets = [load_json(Path(f)) for f in paths]
    fig = build_figure(datasets)

    output = args.output if args.output.is_absolute() else folder / args.output
    try:
        fig.savefig(output, dpi=140, bbox_inches="tight")
    except OSError:
        fail(
            f"Error: cannot write {output}\n"
            "  Close the PNG if it is open in a viewer, then run the app again."
        )
    ok(f"Saved {output}  ({', '.join(d['file'] for d in datasets)})")

    if args.show:
        plt.show()
    else:
        plt.close(fig)


if __name__ == "__main__":
    main()
