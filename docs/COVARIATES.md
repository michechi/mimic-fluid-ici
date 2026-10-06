# The 64 clinical covariates

Both samples use these 64 original fields: 17 prior-history indicators and 47 other variables. These are clinical input fields before categorical encoding and the addition of training-derived missingness indicators. Treatment, outcome, identifiers, and timestamps used for auditing are not part of this list.

The machine-readable definitions are in `config/covariate_definitions.json`. Timing windows and documentation rules are specified in `DATA_PREPROCESSING.md`.

## Demographics

| Clinical variable | Dataset field |
|---|---|
| Approximate age, capped at 90 years | `x_age` |
| Recorded sex | `x_sex` |

## Admission and ICU context

| Clinical variable | Dataset field |
|---|---|
| ICU care unit at treatment | `x_careunit_at_t0` |
| Approximate calendar period (lower year bound) | `x_calendar_year_low` |
| Hours since ICU admission | `x_hours_since_icu` |
| Hospital admission type | `x_admission_type` |
| Hospital admission source | `x_admission_location` |
| Hours since hospital admission | `x_hours_since_hospital` |
| Number of earlier observed hospitalizations | `x_prior_hospitalizations` |

## Infection-related timing

| Clinical variable | Dataset field |
|---|---|
| Hours since latest antimicrobial administration | `x_hours_since_antibiotic` |
| Hours since latest blood-culture collection | `x_hours_since_blood_culture` |

## Vital signs and weight

| Clinical variable | Dataset field |
|---|---|
| Mean arterial pressure | `x_map_last_value` |
| Heart rate | `x_heart_rate_last_value` |
| Respiratory rate | `x_resp_rate_last_value` |
| Temperature | `x_temperature_last_value` |
| Peripheral oxygen saturation | `x_spo2_last_value` |
| Body weight | `x_weight_last_value` |

## Glasgow Coma Scale components

| Clinical variable | Dataset field |
|---|---|
| Eye response | `x_gcs_eye_last_value` |
| Verbal response | `x_gcs_verbal_last_value` |
| Motor response | `x_gcs_motor_last_value` |

## Laboratory measurements

| Clinical variable | Dataset field |
|---|---|
| Lactate | `x_lactate_last_value` |
| Creatinine | `x_creatinine_last_value` |
| Sodium | `x_sodium_last_value` |
| Chloride | `x_chloride_last_value` |
| Bicarbonate | `x_bicarbonate_last_value` |
| Potassium | `x_potassium_last_value` |
| Blood urea nitrogen | `x_bun_last_value` |
| Glucose | `x_glucose_lab_last_value` |
| Hemoglobin | `x_hemoglobin_last_value` |
| Platelet count | `x_platelets_last_value` |
| White blood cell count | `x_wbc_last_value` |
| Albumin | `x_albumin_last_value` |
| Anion gap | `x_anion_gap_last_value` |
| Bilirubin | `x_bilirubin_last_value` |
| International normalized ratio | `x_inr_last_value` |
| Partial thromboplastin time | `x_ptt_last_value` |
| Blood-gas pH | `x_ph_blood_last_value` |
| Alanine aminotransferase | `x_alt_last_value` |
| Aspartate aminotransferase | `x_ast_last_value` |

## Prior fluids, organ support, and urine output

| Clinical variable | Dataset field |
|---|---|
| Number of documented active vasopressors | `x_pressor_drugs_active_documented` |
| Recorded prior saline volume | `x_recorded_prior_ns_ml` |
| Recorded prior lactated Ringer's volume | `x_recorded_prior_lr_ml` |
| Maximum documented ongoing saline rate | `x_ongoing_ns_max_rate_ml_h` |
| Maximum documented ongoing lactated Ringer's rate | `x_ongoing_lr_max_rate_ml_h` |
| Recorded net urine volume, previous 6 hours | `x_recorded_urine_ml_6h` |
| Latest oxygen-delivery device | `x_oxygen_device_last` |
| Charted evidence of renal replacement therapy | `x_rrt_chart_evidence_6h` |

## Medical history from earlier hospitalizations

| Clinical variable | Dataset field |
|---|---|
| Myocardial infarction | `x_history_myocardial_infarct` |
| Congestive heart failure | `x_history_congestive_heart_failure` |
| Peripheral vascular disease | `x_history_peripheral_vascular_disease` |
| Cerebrovascular disease | `x_history_cerebrovascular_disease` |
| Dementia | `x_history_dementia` |
| Chronic pulmonary disease | `x_history_chronic_pulmonary_disease` |
| Rheumatic disease | `x_history_rheumatic_disease` |
| Peptic ulcer disease | `x_history_peptic_ulcer_disease` |
| Mild liver disease | `x_history_mild_liver_disease` |
| Diabetes without chronic complications | `x_history_diabetes_without_cc` |
| Diabetes with chronic complications | `x_history_diabetes_with_cc` |
| Hemiplegia or paraplegia | `x_history_paraplegia` |
| Renal disease | `x_history_renal_disease` |
| Malignancy | `x_history_malignant_cancer` |
| Moderate or severe liver disease | `x_history_severe_liver_disease` |
| Metastatic solid tumor | `x_history_metastatic_solid_tumor` |
| HIV/AIDS | `x_history_aids` |
