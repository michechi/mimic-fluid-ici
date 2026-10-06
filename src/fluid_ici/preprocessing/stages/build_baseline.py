"""Build an auditable baseline table; every X is restricted to pre-t0 evidence."""
import json,re
from .settings import *
con=connect()
save(con,'baseline_context',f'''SELECT p.decision_id,p.subject_id,p.hadm_id,p.stay_id,p.t0,p.A,
p.recorded_index_ml,p.index_records,
p.age_approx x_age,p.anchor_age=91 x_age_topcoded,p.gender x_sex,
p.admission_type x_admission_type,p.admission_location x_admission_location,
p.hours_since_icu x_hours_since_icu,p.hours_since_hospital x_hours_since_hospital,
p.edregtime<p.intime x_ed_before_icu,
(cast(substr(p.anchor_year_group,1,4) AS INTEGER)+year(p.t0)-p.anchor_year)::INTEGER x_calendar_year_low,
(cast(right(p.anchor_year_group,4) AS INTEGER)+year(p.t0)-p.anchor_year)::INTEGER calendar_year_high,
coalesce(u.careunit,p.first_careunit) x_careunit_at_t0,
coalesce(u.n_matches,0) unit_matches,u.careunit IS NULL unit_fallback,
s.curr_service x_current_service,
epoch(p.t0-p.latest_abx_time)/3600 x_hours_since_antibiotic,
epoch(p.t0-p.latest_culture_time)/3600 x_hours_since_blood_culture,
p.map_min_2h x_map_min_2h,p.sbp_min_2h x_sbp_min_2h,
coalesce(p.active_pressor_drugs,0) x_pressor_drugs_active_documented,
p.abx_icu_input_24h abx_icu_source,p.abx_emar_24h abx_emar_source,
p.latest_abx_time,p.latest_abx_available,p.latest_culture_time,p.bp_latest_available,p.pressor_latest_recorded
FROM {pq('primary_index')} p
LEFT JOIN LATERAL (SELECT careunit,count(*) OVER() n_matches FROM {pq('transfers')} t
WHERE t.hadm_id=p.hadm_id AND t.intime<=p.t0 AND (t.outtime>p.t0 OR t.outtime IS NULL)
AND t.careunit IS NOT NULL ORDER BY t.intime DESC,t.transfer_id DESC LIMIT 1) u ON true
LEFT JOIN LATERAL (SELECT curr_service FROM {pq('services')} s WHERE s.hadm_id=p.hadm_id
AND s.transfertime<p.t0 ORDER BY s.transfertime DESC LIMIT 1) s ON true''')

vital_variables=['heart_rate','sbp','dbp','map','resp_rate','temperature','spo2','weight',
 'gcs_eye','gcs_verbal','gcs_motor','fio2','peep','oxygen_flow']
save(con,'baseline_vitals_long',f'''SELECT p.decision_id,x.variable,
avg(x.x) FILTER(WHERE x.charttime>=p.t0-INTERVAL 6 HOUR) mean_6h,
min(x.x) FILTER(WHERE x.charttime>=p.t0-INTERVAL 6 HOUR) min_6h,
max(x.x) FILTER(WHERE x.charttime>=p.t0-INTERVAL 6 HOUR) max_6h,
arg_max(x.x,struct_pack(chart:=x.charttime,stored:=x.storetime,item:=x.itemid)) last_value,
epoch(p.t0-max(x.charttime))/3600 hours_since_last,
count(*) n_observations,max(x.available_time) latest_available
FROM {pq('primary_index')} p JOIN {pq('vitals_clean')} x
ON p.stay_id=x.stay_id AND x.charttime<p.t0 AND x.available_time<p.t0
AND x.charttime>=p.t0-CASE WHEN x.variable='weight' THEN INTERVAL 24 HOUR ELSE INTERVAL 6 HOUR END
GROUP BY p.decision_id,x.variable,p.t0''')
fields=[]
for v in vital_variables:
    for stat in ['last_value','hours_since_last','n_observations']:
        fields.append(f'max({stat}) FILTER(WHERE variable={sqlstr(v)}) AS x_{v}_{stat}')
    if v in ['heart_rate','sbp','map','resp_rate','temperature','spo2']:
        for stat in ['min_6h','max_6h','mean_6h']:
            fields.append(f'max({stat}) FILTER(WHERE variable={sqlstr(v)}) AS x_{v}_{stat}')
save(con,'baseline_vitals',f'''SELECT decision_id,{','.join(fields)},max(latest_available) vitals_latest_available
FROM {pq('baseline_vitals_long')} GROUP BY decision_id''')

# Keep standard serum/plasma analytes separate from whole-blood gas counterparts.
lab_map={50862:'albumin',50868:'anion_gap',50882:'bicarbonate',51006:'bun',50902:'chloride',
50912:'creatinine',50931:'glucose_lab',50983:'sodium',50971:'potassium',50885:'bilirubin',
51221:'hematocrit',51222:'hemoglobin',51265:'platelets',51301:'wbc',51237:'inr',51275:'ptt',
50813:'lactate',50820:'ph_blood',50861:'alt',50878:'ast'}
case='CASE '+ ' '.join(f'WHEN l.itemid={i} THEN {sqlstr(v)}' for i,v in lab_map.items())+' END'
save(con,'baseline_labs_long',f'''WITH le AS (SELECT p.decision_id,p.t0,l.*,{case} AS variable
FROM {pq('primary_index')} p JOIN {pq('labs')} l
ON p.subject_id=l.subject_id AND (p.hadm_id=l.hadm_id OR l.hadm_id IS NULL)
AND l.charttime>=p.t0-INTERVAL 24 HOUR AND l.charttime<p.t0 AND l.storetime<p.t0
AND l.charttime>=coalesce(least(p.admittime,p.edregtime),p.admittime)
WHERE l.itemid IN ({','.join(map(str,lab_map))})
AND l.valuenum IS NOT NULL AND (l.valuenum>0 OR l.itemid=50868)
AND CASE WHEN l.itemid=50862 THEN l.valuenum<=10
WHEN l.itemid=51006 THEN l.valuenum<=300
WHEN l.itemid=50912 THEN l.valuenum<=150
WHEN l.itemid=50983 THEN l.valuenum<=200
WHEN l.itemid=50971 THEN l.valuenum<=30
WHEN l.itemid=50820 THEN l.valuenum BETWEEN 6.5 AND 8.5
ELSE l.valuenum<=10000 END)
SELECT decision_id,variable,
arg_max(valuenum,struct_pack(chart:=charttime,stored:=storetime,id:=labevent_id)) last_value,
min(valuenum) min_24h,max(valuenum) max_24h,epoch(t0-max(charttime))/3600 hours_since_last,
count(*) n_observations,max(greatest(charttime,storetime)) latest_available
FROM le GROUP BY decision_id,variable,t0''')
fields=[]
for v in lab_map.values():
    for stat in ['last_value','hours_since_last']:
        fields.append(f'max({stat}) FILTER(WHERE variable={sqlstr(v)}) AS x_{v}_{stat}')
    if v in ['creatinine','chloride','lactate','potassium','sodium']:
        for stat in ['min_24h','max_24h']:
            fields.append(f'max({stat}) FILTER(WHERE variable={sqlstr(v)}) AS x_{v}_{stat}')
save(con,'baseline_labs',f'''SELECT decision_id,{','.join(fields)},max(latest_available) labs_latest_available
FROM {pq('baseline_labs_long')} GROUP BY decision_id''')

# Delivered volumes only for completed, recorded pre-t0 events. No proportional
# allocation of a later-recorded total volume from an infusion crossing t0.
save(con,'baseline_fluids',f'''SELECT p.decision_id,
count(*) FILTER(WHERE f.itemid IN (225158,225828) AND f.ordercategoryname='03-IV Fluid Bolus'
AND f.endtime<p.t0 AND f.storetime<p.t0) x_prior_bolus_records,
coalesce(sum(f.ml) FILTER(WHERE f.itemid=225158 AND f.endtime<p.t0 AND f.storetime<p.t0),0) x_recorded_prior_ns_ml,
coalesce(sum(f.ml) FILTER(WHERE f.itemid=225828 AND f.endtime<p.t0 AND f.storetime<p.t0),0) x_recorded_prior_lr_ml,
coalesce(sum(f.ml) FILTER(WHERE f.itemid=225158 AND f.endtime<p.t0 AND f.storetime<p.t0 AND f.starttime>=p.t0-INTERVAL 6 HOUR),0) x_recorded_ns_ml_6h,
coalesce(sum(f.ml) FILTER(WHERE f.itemid=225828 AND f.endtime<p.t0 AND f.storetime<p.t0 AND f.starttime>=p.t0-INTERVAL 6 HOUR),0) x_recorded_lr_ml_6h,
arg_max(CASE WHEN f.itemid=225828 THEN 1 ELSE 0 END,f.starttime)
FILTER(WHERE f.itemid IN (225158,225828) AND f.storetime<p.t0 AND f.ordercategoryname='03-IV Fluid Bolus') x_previous_bolus_lr,
count(*) FILTER(WHERE f.itemid IN (225158,225828) AND f.storetime>=p.t0) prior_fluid_records_entered_after_t0,
count(*) FILTER(WHERE f.itemid IN (225158,225828) AND f.storetime<p.t0 AND f.endtime>p.t0) x_ongoing_crystalloid_records_documented,
count(*) FILTER(WHERE f.itemid IN (226361,226363,226364,226375) AND f.storetime<p.t0) x_prior_non_icu_intake_summary_records,
max(f.storetime) FILTER(WHERE f.storetime<p.t0) fluids_latest_available
FROM {pq('primary_index')} p LEFT JOIN {pq('fluid_inputs')} f
ON p.stay_id=f.stay_id AND f.starttime<p.t0 AND f.ml>0
AND f.statusdescription IS DISTINCT FROM 'Rewritten'
AND (f.ordercomponenttypedescription='Main order parameter' OR f.itemid IN (226361,226363,226364,226375))
GROUP BY p.decision_id''')
save(con,'baseline_urine',f'''SELECT p.decision_id,sum(u.urine_ml) x_recorded_urine_ml_6h,
count(u.urine_ml) x_urine_records_6h,
epoch(max(u.charttime)-min(u.charttime))/3600 x_urine_observation_span_hours,
max(greatest(u.charttime,u.storetime)) urine_latest_available
FROM {pq('primary_index')} p LEFT JOIN {pq('urine')} u
ON p.stay_id=u.stay_id AND u.charttime>=p.t0-INTERVAL 6 HOUR
AND u.charttime<p.t0 AND u.storetime<p.t0 AND u.valueuom='mL'
GROUP BY p.decision_id''')

# Point-in-time support indicators; no future-derived ventilation end intervals.
save(con,'baseline_support',f'''SELECT p.decision_id,
arg_max(c.value,struct_pack(chart:=c.charttime,stored:=c.storetime)) FILTER(WHERE c.itemid=226732) x_oxygen_device_last,
arg_max(c.value,struct_pack(chart:=c.charttime,stored:=c.storetime)) FILTER(WHERE c.itemid IN (223849,229314)) x_ventilator_mode_last,
max(CASE WHEN c.itemid IN (226499,224154,225183,227438,224191,225806,225807,228004,228005,228006,224144,224145,224153,226457)
OR (c.itemid=225965 AND c.value='In use') THEN 1 ELSE 0 END) x_rrt_chart_evidence_6h,
max(greatest(c.charttime,c.storetime)) support_latest_available
FROM {pq('primary_index')} p LEFT JOIN {pq('charts')} c
ON p.stay_id=c.stay_id AND c.charttime>=p.t0-INTERVAL 6 HOUR AND c.charttime<p.t0 AND c.storetime<p.t0
AND c.itemid IN (226732,223849,229314,225965,226499,224154,225183,227438,224191,225806,225807,228004,228005,228006,224144,224145,224153,226457)
GROUP BY p.decision_id''')
save(con,'baseline_pressors',f'''SELECT p.decision_id,
count(DISTINCT i.itemid) FILTER(WHERE m.vasopressor) x_pressor_drugs_recorded_6h,
count(*) FILTER(WHERE m.dobutamine) x_dobutamine_records_6h,
arg_max(i.rate,struct_pack(start:=i.starttime,stored:=i.storetime))
FILTER(WHERE i.itemid=221906 AND i.rateuom='mcg/kg/min') x_norepinephrine_last_mcg_kg_min,
max(i.storetime) pressor_history_latest_available
FROM {pq('primary_index')} p LEFT JOIN {pq('drug_inputs')} i
ON p.stay_id=i.stay_id AND i.starttime<p.t0 AND i.endtime>=p.t0-INTERVAL 6 HOUR
AND i.storetime<p.t0 AND i.rate>0 AND i.statusdescription IS DISTINCT FROM 'Rewritten'
LEFT JOIN {pq('input_drug_map')} m USING(itemid)
GROUP BY p.decision_id''')

# Historical ICD evidence uses only earlier hospitalizations already completed
# before this admission. The current admission's discharge diagnoses are excluded.
save(con,'admission_history_dates',f'''SELECT subject_id::BIGINT subject_id,hadm_id::BIGINT hadm_id,
admittime::TIMESTAMP admittime,dischtime::TIMESTAMP dischtime FROM {raw('hosp/admissions')}''')
save(con,'prior_hospitalizations',f'''SELECT p.decision_id,a.hadm_id,a.dischtime
FROM {pq('primary_index')} p JOIN {pq('admission_history_dates')} a
ON p.subject_id=a.subject_id AND a.dischtime<p.admittime AND a.hadm_id<>p.hadm_id''')
save(con,'history_diagnoses',f'''SELECT hadm_id::BIGINT hadm_id,icd_code,icd_version::INTEGER icd_version
FROM {raw('hosp/diagnoses_icd')} WHERE hadm_id::BIGINT IN (SELECT hadm_id FROM {pq('prior_hospitalizations')})''')
charlson=(REF/'comorbidity__charlson.sql').read_text()
prefix=charlson[:charlson.index(', ag AS')]
prefix=prefix.replace('`physionet-data.mimiciv_hosp.diagnoses_icd`',pq('history_diagnoses'))
prefix=prefix.replace('`physionet-data.mimiciv_hosp.admissions`',f'(SELECT DISTINCT hadm_id FROM {pq("prior_hospitalizations")})')
save(con,'history_charlson_hadm',prefix+' SELECT * FROM com')
names=[x[0] for x in con.execute(f'DESCRIBE SELECT * FROM {pq("history_charlson_hadm")}').fetchall() if x[0]!='hadm_id']
save(con,'baseline_history',f'''SELECT p.decision_id,count(h.hadm_id) x_prior_hospitalizations,
{','.join(f'max(c.{n}) AS x_history_{n}' for n in names)},max(h.dischtime) history_latest_discharge
FROM {pq('primary_index')} p LEFT JOIN {pq('prior_hospitalizations')} h USING(decision_id)
LEFT JOIN {pq('history_charlson_hadm')} c ON c.hadm_id=h.hadm_id
GROUP BY p.decision_id''')
tables=['baseline_vitals','baseline_labs','baseline_fluids','baseline_urine','baseline_support','baseline_pressors','baseline_history']
query=f'SELECT b.*,'+','.join(f't{i}.* EXCLUDE(decision_id)' for i in range(len(tables)))+f' FROM {pq("baseline_context")} b '
query+=' '.join(f'LEFT JOIN {pq(t)} t{i} USING(decision_id)' for i,t in enumerate(tables))
save(con,'analysis_baseline',query)
df=con.execute(f'SELECT * FROM {pq("analysis_baseline")}').fetchdf()
assert df.decision_id.is_unique and df.subject_id.is_unique
assert len(df)==con.execute(f'SELECT count(*) FROM {pq("primary_index")}').fetchone()[0]
timing_cols=[x for x in df if x.endswith('latest_available')]+['latest_abx_available','latest_culture_time','bp_latest_available','pressor_latest_recorded','history_latest_discharge']
violations={col:int((df[col].notna() & (df[col]>=df.t0)).sum()) for col in timing_cols}
assert not any(violations.values()),violations
summary={'n':len(df),'columns':len(df.columns),'candidate_covariates':sum(x.startswith('x_') for x in df),
'pretreatment_timing_violations':violations,
'missing_fraction':{x:float(df[x].isna().mean()) for x in df if x.startswith('x_')},
'unit_distribution':df.groupby('x_careunit_at_t0').agg(n=('A','size'),lr_fraction=('A','mean')).reset_index().to_dict('records'),
'unit_fallback':int(df.unit_fallback.sum()),'unit_multiple_matches':int((df.unit_matches>1).sum())}
(OUT/'baseline_quality.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='missing_fraction'},indent=2),flush=True)
