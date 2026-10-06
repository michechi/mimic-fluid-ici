#!/usr/bin/env python3
"""Export two-sample aggregate curves as self-contained PGFPlots figures."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

SAMPLES = ("imputed_sample", "complete_case_sample")
TITLES = ("Imputed sample", "Complete-case sample")
CHIS = ((0.02, "002", "595959"), (0.10, "010", "858585"),
        (0.25, "025", "B3B3B3"), (1.00, "100", "DBDBDB"))
PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[a4paper,margin=18mm]{geometry}
\usepackage{xcolor}
\usepackage{pgfplots}
\usepackage{pgfplotstable}
\usepgfplotslibrary{fillbetween,groupplots}
\pgfplotsset{compat=1.18}
\pagestyle{empty}
"""


def number(value):
    return format(float(value), ".17g")


def load_curves(path):
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"analysis", "delta", "chi", "n", "p", "ipi_difference_pp",
                "lower_difference_pp", "upper_difference_pp", "ipi_lr_probability"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("The input must be a nonempty aggregate curves.csv with the expected columns.")
    if {row["analysis"] for row in rows} != set(SAMPLES):
        raise ValueError("Expected exactly imputed_sample and complete_case_sample.")
    selected = {}
    grids = []
    for sample in SAMPLES:
        population = [r for r in rows if r["analysis"] == sample]
        if len({r["n"] for r in population}) != 1 or len({r["p"] for r in population}) != 1:
            raise ValueError("Inconsistent sample metadata.")
        grouped = {}
        for row in population:
            numeric = {key: float(row[key]) for key in required if key != "analysis"}
            if not all(math.isfinite(v) for v in numeric.values()):
                raise ValueError("Nonfinite plotting value.")
            key = (numeric["delta"], round(numeric["chi"], 12))
            if key in grouped:
                raise ValueError("Duplicate delta/chi rows.")
            grouped[key] = numeric
        delta = sorted({key[0] for key in grouped})
        grids.append(delta)
        if not any(abs(d) < 1e-12 for d in delta):
            raise ValueError("The grid must include delta=0.")
        data = []
        for d in delta:
            zero = grouped[(d, 0.0)]
            row = dict(delta=d, ipi=zero["ipi_difference_pp"], lr=100*zero["ipi_lr_probability"])
            last_lo, last_hi = row["ipi"], row["ipi"]
            for chi, suffix, _ in CHIS:
                bound = grouped[(d, chi)]
                lo, hi = bound["lower_difference_pp"], bound["upper_difference_pp"]
                if lo > last_lo+1e-8 or hi < last_hi-1e-8:
                    raise ValueError("Selected sensitivity regions are not nested.")
                if abs(bound["ipi_difference_pp"]-row["ipi"]) > 1e-8:
                    raise ValueError("IPI depends on chi in the input.")
                if abs(d) < 1e-12 and max(abs(lo), abs(hi), abs(row["ipi"])) > 1e-8:
                    raise ValueError("Contrasts must vanish at delta=0.")
                row[f"lower{suffix}"], row[f"upper{suffix}"] = lo, hi
                last_lo, last_hi = lo, hi
            if not 0 <= row["lr"] <= 100:
                raise ValueError("LR proportion is outside [0,100].")
            data.append(row)
        selected[sample] = dict(n=int(float(population[0]["n"])),
                                p=int(float(population[0]["p"])), rows=data)
    if grids[0] != grids[1]:
        raise ValueError("Samples use different delta grids.")
    return selected


def table(rows, name, mortality):
    fields = ["delta", "ipi"] if mortality else ["delta", "lr"]
    if mortality:
        fields += [f"{side}{suffix}" for _, suffix, _ in CHIS for side in ["lower", "upper"]]
    lines = [r"\pgfplotstableread[col sep=space, row sep=\\]{", " ".join(fields)+r" \\"]
    lines += [" ".join(number(row[field]) for field in fields)+r" \\" for row in rows]
    lines.append("}\\"+name)
    return "\n".join(lines)


def figure(data, mortality):
    values = [row[field] for item in data.values() for row in item["rows"]
              for field in (["lower100", "upper100"] if mortality else ["lr"])]
    low, high = min(values), max(values)
    span = high-low or 1
    low, high = low-.08*span, high+.08*span
    xmin = min(r["delta"] for r in data[SAMPLES[0]]["rows"])
    xmax = max(r["delta"] for r in data[SAMPLES[0]]["rows"])
    lines = [r"\begin{figure}[tbp]", r"\centering", r"\begingroup",
             r"\definecolor{fluidIPI}{HTML}{0000FF}"]
    lines += [rf"\definecolor{{fluidChi{suffix}}}{{HTML}}{{{rgb}}}" for _, suffix, rgb in CHIS]
    lines += [r"\pgfplotsset{fluid swatch/.style={legend image code/.code={",
              r"  \path[##1,draw=none] (0cm,-0.08cm) rectangle (0.45cm,0.08cm);}}}"]
    for i, sample in enumerate(SAMPLES):
        lines.append(table(data[sample]["rows"], f"fluidTable{'One' if i==0 else 'Two'}", mortality))
    ylabel = "Mortality difference (percentage points)" if mortality else "Patients receiving LR (\\%)"
    lines += [r"\begin{tikzpicture}", r"\begin{groupplot}[",
              r"group style={group size=2 by 1,horizontal sep=0.13\textwidth},",
              r"width=0.405\textwidth,height=6.4cm,scale only axis,",
              "xmin="+number(xmin)+",xmax="+number(xmax)+",",
              "ymin="+number(low)+",ymax="+number(high)+",",
              r"xlabel={$\delta$},ylabel={"+ylabel+r"},",
              r"xtick={-1.3862943611198906,-0.6931471805599453,0,0.6931471805599453,1.3862943611198906},",
              r"xticklabels={$-1.39$,$-0.69$,$0$,$0.69$,$1.39$},",
              r"tick label style={font=\scriptsize},label style={font=\small},",
              r"title style={font=\small,align=center},",
              r"scaled ticks=false,axis on top=false,clip=true,",
              r"legend columns=5,legend style={draw=none,font=\footnotesize,",
              r"at={(1.16,1.30)},anchor=south,column sep=3pt,cells={anchor=west}}",
              "]"]
    for i, sample in enumerate(SAMPLES):
        item = data[sample]
        sample_n = format(item["n"], ",").replace(",", "{,}")
        title = TITLES[i]+rf"\\$n={sample_n}$"
        second = ",ylabel={},yticklabels={}" if i == 1 else ""
        lines.append(r"\nextgroupplot[title={"+title+"}"+second+"]")
        tab = r"\fluidTableOne" if i == 0 else r"\fluidTableTwo"
        if mortality:
            for _, suffix, _ in CHIS:
                for side in ["lower", "upper"]:
                    path = f"fluid{i}{side}{suffix}"
                    lines += [rf"\addplot[draw=none,name path={path},forget plot]",
                              rf"table[x=delta,y={side}{suffix}] {{{tab}}};"]
            for _, suffix, _ in reversed(CHIS):
                lines += [rf"\addplot[draw=none,fill=fluidChi{suffix},fill opacity=1,forget plot]",
                          rf"fill between[of=fluid{i}lower{suffix} and fluid{i}upper{suffix}];"]
            lines.append(r"\addplot[gray,densely dotted,line width=0.4pt,forget plot] coordinates {("
                         +number(xmin)+",0) ("+number(xmax)+",0)};")
        lines.append(r"\addplot[gray!50,densely dotted,line width=0.4pt,forget plot] coordinates {(0,"
                     +number(low)+") (0,"+number(high)+")};")
        if mortality:
            for _, suffix, _ in CHIS:
                for side in ["lower", "upper"]:
                    lines += [rf"\addplot[fluidChi{suffix},dashed,line width=0.55pt,no marks,forget plot]",
                              rf"table[x=delta,y={side}{suffix}] {{{tab}}};"]
        lines += [r"\addplot[fluidIPI,line width=0.9pt,no marks,forget plot]",
                  "table[x=delta,y="+("ipi" if mortality else "lr")+"] {"+tab+"};"]
        if i == 0 and mortality:
            lines += [r"\addlegendimage{fluidIPI,line width=0.9pt,no marks}", r"\addlegendentry{IPI}"]
            for chi, suffix, _ in CHIS:
                lines += [rf"\addlegendimage{{fluid swatch,fill=fluidChi{suffix},draw=none}}",
                          rf"\addlegendentry{{$\chi={chi:.2f}$}}"]
    lines += [r"\end{groupplot}", r"\end{tikzpicture}", r"\endgroup"]
    if mortality:
        caption = (r"Mortality differences under incremental interventions on lactated Ringer's use, relative to each sample's current practice ($\delta=0$). "
                   r"Blue curves show the fitted-law IPI estimates. Gray regions are ICI mechanism-sensitivity regions for $\chi=0.02,0.10,0.25,1.00$, "
                   r"with matching dashed boundaries. These regions are not sampling confidence intervals.")
        label = "fig:fluid-mortality-comparison"
    else:
        caption = (r"Estimated lactated Ringer's use under incremental interventions in the imputed and complete-case samples. "
                   r"The intervention multiplies conditional treatment odds by $e^\delta$; $\delta=0$ represents current practice.")
        label = "fig:fluid-lr-use-comparison"
    lines += [r"\caption{"+caption+"}", r"\label{"+label+"}", r"\end{figure}", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent
    output = args.output_dir.resolve()
    if output == repo or repo in output.parents:
        parser.error("Export figures outside the repository.")
    source = args.results_dir.resolve()/"curves.csv"
    data = load_curves(source)
    outputs = {}
    for stem, mortality in [("mortality_sensitivity", True), ("lr_use", False)]:
        fragment = figure(data, mortality)
        outputs[stem+"_figure.tex"] = fragment
        outputs[stem+"_preview.tex"] = PREAMBLE+r"\begin{document}"+"\n"+fragment+r"\end{document}"+"\n"
    output.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        path = output/name
        if path.exists() and path.read_text() != content:
            raise FileExistsError(f"Existing export differs: {path}. Choose a new output directory.")
    for name, content in outputs.items():
        (output/name).write_text(content)
    report = dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  samples={name: {"n": item["n"], "p": item["p"], "delta_count": len(item["rows"])} for name, item in data.items()},
                  chi_levels=[chi for chi, _, _ in CHIS], embedded_tables=True,
                  shared_y_axes=True, no_sampling_confidence_intervals=True,
                  files={name: hashlib.sha256(content.encode()).hexdigest() for name, content in outputs.items()})
    (output/"latex_export_validation.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
