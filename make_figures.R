#!/usr/bin/env Rscript
# Plot publishable aggregates only. No patient data or fitted models are read.
# Rscript make_figures.R --results-dir /path/run/results --output-dir /path/run/figures
if (!requireNamespace("ggplot2", quietly = TRUE)) stop("Install ggplot2 before plotting.")
suppressPackageStartupMessages(library(ggplot2))
analysis_order <- c("imputed_sample", "complete_case_sample")
analysis_titles <- c(imputed_sample = "Imputed sample", complete_case_sample = "Complete-case sample")
read_comparison_curves <- function(path) {
  d <- read.csv(path, check.names = FALSE, stringsAsFactors = FALSE)
  numeric_fields <- c("delta", "odds_multiplier", "chi", "lower_risk", "ipi_risk",
                      "upper_risk", "lower_difference_pp", "ipi_difference_pp",
                      "upper_difference_pp", "plugin_baseline_risk",
                      "ipi_lr_probability", "n", "p")
  required <- c("analysis", numeric_fields)
  if (!all(required %in% names(d))) {
    stop("Missing columns: ", paste(setdiff(required, names(d)), collapse = ", "))
  }
  if (!all(vapply(d[numeric_fields], is.numeric, logical(1))) ||
      !all(is.finite(as.matrix(d[numeric_fields])))) {
    stop("All numeric columns must be finite numeric values.")
  }
  if (!setequal(unique(d$analysis), analysis_order)) stop("Expected exactly imputed_sample and complete_case_sample.")
  present_analyses <- analysis_order
  if (anyDuplicated(d[c("analysis", "delta", "chi")])) stop("Duplicate curve rows.")
  tol <- 1e-7
  if (any(d$chi < 0 | d$chi > 1)) stop("chi must be in [0, 1].")
  if (any(abs(d$odds_multiplier - exp(d$delta)) > tol)) {
    stop("delta must be the signed log-odds shift, with odds_multiplier = exp(delta).")
  }
  if (any(d$n <= 0 | d$p <= 0 | d$n != round(d$n) | d$p != round(d$p))) {
    stop("n and p must be positive integers.")
  }
  probs <- as.matrix(d[c("lower_risk", "ipi_risk", "upper_risk",
                         "plugin_baseline_risk", "ipi_lr_probability")])
  if (any(probs < -tol | probs > 1 + tol)) stop("Risk inputs must be fractions in [0, 1].")
  for (prefix in c("lower", "ipi", "upper")) {
    expected <- 100 * (d[[paste0(prefix, "_risk")]] - d$plugin_baseline_risk)
    if (max(abs(expected - d[[paste0(prefix, "_difference_pp")]])) > tol) {
      stop("Risk and contrast columns disagree for ", prefix, ".")
    }
  }
  for (code in present_analyses) {
    a <- d[d$analysis == code, ]
    if (length(unique(a$n)) != 1L || length(unique(a$p)) != 1L ||
        diff(range(a$plugin_baseline_risk)) > tol) stop("Inconsistent analysis metadata.")
    ch <- sort(unique(a$chi))
    del <- sort(unique(a$delta))
    if (min(ch) != 0 || max(ch) != 1 || !any(abs(del) < 1e-10)) {
      stop("Each analysis needs chi=0, chi=1, and delta=0.")
    }
    for (delta_value in del) {
      a_d <- a[a$delta == delta_value, ]
      a_d <- a_d[order(a_d$chi), ]
      if (!identical(a_d$chi, ch)) stop("Incomplete delta-by-chi grid.")
      if (any(diff(a_d$lower_difference_pp) > tol) ||
          any(diff(a_d$upper_difference_pp) < -tol)) stop("Non-nested chi intervals.")
      if (diff(range(a_d$ipi_difference_pp)) > tol ||
          diff(range(a_d$ipi_lr_probability)) > tol) stop("IPI must not vary with chi.")
      if (any(a_d$lower_difference_pp > a_d$ipi_difference_pp + tol) ||
          any(a_d$upper_difference_pp < a_d$ipi_difference_pp - tol)) {
        stop("A sensitivity interval excludes its IPI reference.")
      }
      if (abs(a_d$lower_difference_pp[1] - a_d$ipi_difference_pp[1]) > tol ||
          abs(a_d$upper_difference_pp[1] - a_d$ipi_difference_pp[1]) > tol) {
        stop("At chi=0 the sensitivity interval must collapse to the IPI.")
      }
    }
    z <- a[abs(a$delta) < 1e-10, ]
    if (max(abs(as.matrix(z[c("lower_difference_pp", "ipi_difference_pp",
                              "upper_difference_pp")]))) > tol) {
      stop("All mortality contrasts must vanish at delta=0.")
    }
    ipi_a <- a[a$chi == 0, ]
    ipi_a <- ipi_a[order(ipi_a$delta), ]
    if (any(diff(ipi_a$ipi_lr_probability) < -tol)) stop("LR use must increase with delta.")
  }
  grids <- lapply(present_analyses, function(code) sort(unique(d$delta[d$analysis == code])))
  if (!all(vapply(grids, identical, logical(1), y = grids[[1]]))) {
    stop("The analyses must use the same delta grid.")
  }
  d$analysis <- factor(d$analysis, levels = present_analyses)
  d[order(d$analysis, d$delta, d$chi), ]
}

figure_theme <- function() {
  theme_classic(base_size = 11, base_family = "sans") +
    theme(axis.text = element_text(colour = "black", size = 10),
          axis.title.x = element_text(margin = margin(t = 8)),
          axis.title.y = element_text(margin = margin(r = 8)),
          axis.line = element_line(linewidth = .35),
          axis.ticks = element_line(linewidth = .35),
          plot.caption = element_text(size = 9, hjust = 0, lineheight = 1.2,
                                      margin = margin(t = 10)),
          plot.margin = margin(10, 14, 8, 10),
          strip.background = element_blank(),
          strip.text = element_text(size = 11, lineheight = 1.15, margin = margin(b = 10)),
          panel.spacing.x = grid::unit(14, "mm"),
          legend.position = "top", legend.box = "horizontal",
          legend.title = element_text(size = 10), legend.text = element_text(size = 10),
          legend.key.width = grid::unit(12, "mm"), legend.key.height = grid::unit(4, "mm"),
          legend.box.margin = margin(b = 8))
}

delta_scale <- function() {
  scale_x_continuous(name = expression(delta), breaks = log(c(.25, .5, 1, 2, 4)),
                     labels = c("-1.39", "-0.69", "0", "0.69", "1.39"),
                     expand = expansion(mult = 0))
}

sample_labels <- function(d) {
  setNames(vapply(analysis_order, function(code) {
    meta <- d[as.character(d$analysis) == code, ][1, ]
    paste0(analysis_titles[[code]], "\nn = ", format(meta$n, big.mark = ",", trim = TRUE),
           "; ", meta$p, " clinical input fields")
  }, character(1)), analysis_order)
}

make_mortality <- function(d) {
  ipi <- d[d$chi == 0, ]
  levels <- c(.02, .10, .25, 1)
  keys <- c("0.02", "0.10", "0.25", "1.00")
  shades <- setNames(gray(c(.35, .52, .70, .86)), keys)
  bounds <- d[Reduce(`|`, lapply(levels, function(ch) abs(d$chi-ch) < 1e-10)), ]
  bounds$chi_key <- factor(sprintf("%.2f", bounds$chi), levels = keys)
  # Large regions are drawn first; smaller regions cover them with darker gray.
  # Both the boundary and its region use the same opaque shade.
  bounds$layer <- match(bounds$chi, rev(levels))
  p <- ggplot() +
    geom_ribbon(data = bounds,
                aes(delta, ymin = lower_difference_pp, ymax = upper_difference_pp,
                    fill = chi_key, group = layer), colour = NA, alpha = 1) +
    geom_hline(yintercept = 0, colour = "grey65", linetype = "dashed", linewidth = .3) +
    geom_vline(xintercept = 0, colour = "grey70", linetype = "dotted", linewidth = .3)
  for (key in keys) {
    rows <- bounds[bounds$chi_key == key, ]
    p <- p +
      geom_line(data = rows, aes(delta, lower_difference_pp),
                colour = shades[[key]], linetype = "dashed", linewidth = .55) +
      geom_line(data = rows, aes(delta, upper_difference_pp),
                colour = shades[[key]], linetype = "dashed", linewidth = .55)
  }
  p + geom_line(data = ipi, aes(delta, ipi_difference_pp, colour = "IPI"), linewidth = .85) +
    facet_wrap(~analysis, nrow = 1, scales = "fixed", labeller = as_labeller(sample_labels(d))) +
    scale_fill_manual(name = expression(chi), values = shades, breaks = keys,
                       guide = guide_legend(order = 2, nrow = 1)) +
    scale_colour_manual(name = NULL, values = c(IPI = "#0000FF"), breaks = "IPI",
                         guide = guide_legend(order = 1, nrow = 1)) +
    delta_scale() +
    scale_y_continuous(name = "Mortality difference (percentage points)",
                       breaks = function(x) pretty(x, n = 6), expand = expansion(mult = .08)) +
    labs(caption = paste0("Differences are relative to each sample's estimated current practice (delta = 0).\n",
                          "Gray regions show mechanism sensitivity, not sampling confidence intervals.")) +
    figure_theme()
}

make_lr_use <- function(d) {
  ipi <- d[d$chi == 0, ]
  ticks <- log(c(.25, .5, 1, 2, 4))
  markers <- ipi[vapply(ipi$delta, function(v) any(abs(v-ticks) < 1e-8), logical(1)), ]
  ggplot(ipi, aes(delta, 100 * ipi_lr_probability)) +
    geom_vline(xintercept = 0, colour = "grey70", linetype = "dotted", linewidth = .3) +
    geom_line(colour = "#0000FF", linewidth = .85) +
    geom_point(data = markers, colour = "#0000FF", size = 1.6) +
    facet_wrap(~analysis, nrow = 1, scales = "fixed", labeller = as_labeller(sample_labels(d))) +
    delta_scale() +
    scale_y_continuous(name = "Estimated patients receiving LR (%)", expand = expansion(mult = .08)) +
    labs(caption = "The intervention multiplies conditional LR odds by exp(delta); delta = 0 represents current practice.") +
    figure_theme()
}

save_plot <- function(plot, stem, height) {
  ggsave(paste0(stem, ".pdf"), plot, width = 10.8, height = height,
         device = grDevices::pdf, family = "Helvetica", useDingbats = FALSE, bg = "white")
  ggsave(paste0(stem, ".png"), plot, width = 10.8, height = height,
         device = "png", dpi = 300, bg = "white")
  saveRDS(plot, paste0(stem, ".rds"))
}

main <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  if (length(args) != 4L || !setequal(args[c(1, 3)], c("--results-dir", "--output-dir"))) {
    stop("Usage: Rscript make_figures.R --results-dir RESULTS --output-dir FIGURES")
  }
  options <- setNames(args[c(2, 4)], args[c(1, 3)])
  input_dir <- normalizePath(options[["--results-dir"]], mustWork = TRUE)
  output_requested <- options[["--output-dir"]]
  flag <- grep("^--file=", commandArgs(), value = TRUE)
  repository <- dirname(normalizePath(sub("^--file=", "", flag[1]), mustWork = TRUE))
  # Resolve an existing ancestor before creating the destination, including any
  # symbolic links in that ancestor, to keep generated files outside this repo.
  ancestor <- output_requested
  suffix <- character()
  while (!dir.exists(ancestor)) {
    suffix <- c(basename(ancestor), suffix)
    parent <- dirname(ancestor)
    if (identical(parent, ancestor)) stop("Cannot resolve output directory.")
    ancestor <- parent
  }
  output_dir <- do.call(file.path, as.list(c(normalizePath(ancestor, mustWork = TRUE), suffix)))
  if (identical(output_dir, repository) || startsWith(output_dir, paste0(repository, .Platform$file.sep))) {
    stop("Use a figure output directory outside the source repository.")
  }
  d <- read_comparison_curves(file.path(input_dir, "curves.csv"))
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
  mortality <- make_mortality(d)
  lr_use <- make_lr_use(d)
  save_plot(mortality, file.path(output_dir, "mortality_sensitivity"), 5.15)
  save_plot(lr_use, file.path(output_dir, "lr_use"), 4.65)
  writeLines(c(capture.output(sessionInfo()), "",
                "Shared scales across the imputed and complete-case samples.",
                "Blue curves: plug-in IPI estimates based on averaged held-out predictions.",
                "Gray fill and dashed boundaries share the shade for each selected chi.",
                "Displayed chi: 0.02, 0.10, 0.25, 1.00; no sampling confidence intervals.",
                "Delta is the signed log-odds shift; the horizontal axis is linear in delta.",
                "Input clinical-field counts precede categorical encoding and missingness indicators.",
                "PASS: complete grids, nested intervals, chi=0 collapse, delta=0 reference, finite risks."),
              file.path(output_dir, "figure_validation.txt"))
  message("Saved mortality_sensitivity and lr_use figures to ", normalizePath(output_dir))
}

if (sys.nframe() == 0L) main()
