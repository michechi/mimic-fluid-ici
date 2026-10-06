# Editable LaTeX figures

The repository provides both native ggplot2 figures and a PGFPlots export.
They read the same two-sample aggregate `curves.csv`; no patient-level data,
model refitting, or external graphics files are required for the LaTeX version.

```sh
python export_latex_figures.py --results-dir /external/run/results --output-dir /external/run/latex
```

The standard-library-only exporter writes:

* `mortality_sensitivity_figure.tex`: ready-to-paste two-panel mortality figure.
* `lr_use_figure.tex`: ready-to-paste two-panel LR-use figure.
* `mortality_sensitivity_preview.tex` and `lr_use_preview.tex`: standalone
  documents containing the same figure source and required packages.
* `latex_export_validation.json`: source/file hashes, sample counts, and grids.

All numerical tables are embedded in each figure. The exporter uses the signed
`delta` values directly on a linear horizontal axis. It uses common vertical
limits across the samples, blue IPI curves, and four nested gray regions at
`chi = 0.02, 0.10, 0.25, 1.00`. The bounds and their corresponding fill use
matching gray colors. The legend sits above the plotting axes. These regions
describe mechanism sensitivity, not sampling confidence intervals.

For a manuscript, add these lines to the preamble:

```latex
\usepackage{xcolor}
\usepackage{pgfplots}
\usepackage{pgfplotstable}
\usepgfplotslibrary{fillbetween,groupplots}
\pgfplotsset{compat=1.18}
```

Paste a `_figure.tex` fragment into the document, or place the fragment beside
the manuscript and use:

```latex
\input{mortality_sensitivity_figure.tex}
\input{lr_use_figure.tex}
```

Each fragment already includes `figure`, `caption`, and `label`. Remove that
wrapper if the manuscript already provides one. The default labels are
`fig:fluid-mortality-comparison` and `fig:fluid-lr-use-comparison`. Panel titles
are “Imputed sample” and “Complete-case sample,” with sample sizes read from the
aggregate data. No historical panel letters are used.

Figure width is relative to `\textwidth`; for a two-column manuscript, use a
`figure*` wrapper for the full-width paired figure. The output folder must be
outside this repository. Existing identical files can be regenerated; different
existing files are not overwritten. Exporting writes LaTeX source but does not
claim successful compilation; compile a preview to validate your TeX environment.
