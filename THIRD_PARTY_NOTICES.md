# Third-party notices

The public antimicrobial and Charlson/Quan reference SQL in `src/fluid_ici/preprocessing/references/` comes from [MIT-LCP/mimic-code](https://github.com/MIT-LCP/mimic-code), pinned to commit `303d26c623dcc9c49cc0f204468d4acc2f063797`.

The original MIT license is retained in that directory as `LICENSE`, including the copyright notice for the MIT Laboratory for Computational Physiology. The bundled `mimic_code_commit.txt` and `extraction_provenance.json` record source identity. The study adapts these public definitions to pretreatment availability and prior completed admissions; it does not use current-admission discharge diagnoses as baseline history.

The license accompanying public concept code does not apply to the MIMIC-IV database. Users must obtain MIMIC-IV 3.1 access independently and follow the associated PhysioNet data-use terms. No database records are redistributed here.

Python and R dependencies retain their respective upstream licenses; their source or installed environments are not bundled in this repository.
