"""Outcome-blind, baseline-only clinical eligibility at every recorded bolus.

Proposed primary: first qualifying decision per person, 6--48 h after ICU entry,
blood culture and systemic antibiotic administration in the preceding 24 h,
and MAP <65 or SBP <90 in the preceding 2 h, or documented ongoing vasopressor.
This is suspected infection with hemodynamic instability, not formal Sepsis-3.
"""
import json
from .settings import *
from .definitions import SYSTEMIC_ROUTES
con=connect()
routes=','.join(sqlstr(x) for x in SYSTEMIC_ROUTES)
save(con,'rx_routes',f'''SELECT hadm_id,pharmacy_id,
bool_or(abx_intent AND upper(trim(route)) IN ({routes})) systemic_abx
FROM {pq('prescriptions_icu')} WHERE pharmacy_id IS NOT NULL GROUP BY ALL''')
save(con,'emar_admin_detail',f'''SELECT emar_id,
bool_or(upper(trim(route)) IN ({routes})) systemic_route_detail,
bool_or(coalesce(try_cast(dose_given AS DOUBLE),0)>0) positive_dose,
bool_or(lower(coalesce(complete_dose_not_given,''))='yes') incomplete
FROM {pq('emar_target_detail')} GROUP BY emar_id''')
save(con,'antibiotic_administrations',f'''SELECT DISTINCT e.subject_id,e.hadm_id,
e.charttime event_time,e.storetime recorded_time,greatest(e.charttime,e.storetime) available_time,
'emar' AS abx_source,e.medication AS drug
FROM {pq('emar_subjects')} e
LEFT JOIN {pq('rx_routes')} r ON e.hadm_id=r.hadm_id AND e.pharmacy_id=r.pharmacy_id
LEFT JOIN {pq('emar_admin_detail')} d USING(emar_id)
WHERE e.abx_name AND e.hadm_id IS NOT NULL AND e.charttime IS NOT NULL AND e.storetime IS NOT NULL
AND e.event_txt IN ('Administered','Delayed Administered','Administered in Other Location',
'Started','Delayed Started','Started in Other Location','Restarted')
AND (coalesce(r.systemic_abx,false) OR coalesce(d.systemic_route_detail,false))
AND (NOT coalesce(d.incomplete,false) OR coalesce(d.positive_dose,false))
AND NOT regexp_matches(lower(e.medication),'cream|ointment|ophth|gel|irrigant|inhal|nebul|mupirocin')
UNION ALL
SELECT i.subject_id,i.hadm_id,i.starttime,i.storetime,greatest(i.starttime,i.storetime),
'icu_input',m.label FROM {pq('drug_inputs')} i JOIN {pq('input_drug_map')} m USING(itemid)
WHERE m.antibiotic AND i.amount>0 AND i.statusdescription IS DISTINCT FROM 'Rewritten'
AND i.storetime IS NOT NULL AND i.starttime IS NOT NULL
AND i.ordercomponenttypedescription='Main order parameter' ''')
save(con,'blood_culture_collection',f'''SELECT subject_id,hadm_id,micro_specimen_id,
min(charttime) event_time FROM {pq('culture_events')}
WHERE spec_type_desc='BLOOD CULTURE' AND charttime IS NOT NULL
GROUP BY subject_id,hadm_id,micro_specimen_id''')
save(con,'vitals_clean',f'''WITH v AS (SELECT *,
CASE WHEN itemid=220045 THEN 'heart_rate'
WHEN itemid IN (220179,220050,225309) THEN 'sbp'
WHEN itemid IN (220180,220051,225310) THEN 'dbp'
WHEN itemid IN (220052,220181,225312) THEN 'map'
WHEN itemid IN (220210,224690) THEN 'resp_rate'
WHEN itemid IN (223761,223762) THEN 'temperature'
WHEN itemid=220277 THEN 'spo2'
WHEN itemid IN (225664,220621,226537) THEN 'glucose_chart'
WHEN itemid IN (226512,224639) THEN 'weight'
WHEN itemid=220739 THEN 'gcs_eye'
WHEN itemid=223900 THEN 'gcs_verbal'
WHEN itemid=223901 THEN 'gcs_motor'
WHEN itemid=223835 THEN 'fio2'
WHEN itemid=224700 THEN 'peep'
WHEN itemid=223834 THEN 'oxygen_flow' END AS variable,
CASE WHEN itemid=223761 THEN (valuenum-32)/1.8
WHEN itemid=223835 AND valuenum>1 THEN valuenum/100 ELSE valuenum END x
FROM {pq('charts')})
SELECT subject_id,hadm_id,stay_id,itemid,charttime,storetime,variable,x,
greatest(charttime,storetime) available_time FROM v
WHERE storetime IS NOT NULL AND charttime IS NOT NULL AND variable IS NOT NULL
AND CASE WHEN variable='heart_rate' THEN x>0 AND x<300
-- Additional study plausibility filters, beyond the broad published concept.
-- Apply before hypotension eligibility; excluded readings become unobserved.
WHEN variable='map' THEN x BETWEEN 20 AND 200
WHEN variable='dbp' THEN x BETWEEN 10 AND 180
WHEN variable='sbp' THEN x BETWEEN 40 AND 300
WHEN variable='resp_rate' THEN x>0 AND x<70
WHEN variable='temperature' THEN x>10 AND x<50
WHEN variable='spo2' THEN x>0 AND x<=100
WHEN variable='weight' THEN x>=20 AND x<=400
WHEN variable='gcs_eye' THEN x BETWEEN 1 AND 4
WHEN variable='gcs_verbal' THEN x BETWEEN 1 AND 5
WHEN variable='gcs_motor' THEN x BETWEEN 1 AND 6
WHEN variable='fio2' THEN x BETWEEN 0.2 AND 1
WHEN variable='peep' THEN x BETWEEN 0 AND 40
WHEN variable='oxygen_flow' THEN x BETWEEN 0 AND 100
ELSE x>0 END''')
save(con,'bolus_decisions',f'''WITH d AS (
SELECT subject_id,hadm_id,stay_id,starttime t0,
count(*) index_records,count(DISTINCT itemid) index_fluid_types,
CASE WHEN count(DISTINCT itemid)=1 THEN max(A) END A,sum(ml) recorded_index_ml
FROM {pq('boluses')} GROUP BY ALL
) SELECT row_number() OVER(ORDER BY subject_id,t0,stay_id) decision_id,d.*,
m.intime,m.outtime,m.gender,m.anchor_age,m.anchor_year,m.anchor_year_group,
m.admittime,m.admission_type,m.admission_location,m.edregtime,m.edouttime,
m.first_careunit,m.race,
epoch(t0-m.intime)/3600 hours_since_icu,
epoch(t0-m.admittime)/3600 hours_since_hospital,
(m.anchor_age+year(t0)-m.anchor_year)::INTEGER age_approx
FROM d JOIN {pq('meta')} m USING(subject_id,hadm_id,stay_id)
LEFT JOIN LATERAL (SELECT careunit FROM {pq('transfers')} tr
WHERE tr.hadm_id=d.hadm_id AND tr.intime<=d.t0 AND (tr.outtime>d.t0 OR tr.outtime IS NULL)
AND tr.careunit IS NOT NULL ORDER BY tr.intime DESC,tr.transfer_id DESC LIMIT 1) u ON true
WHERE t0<m.intime+INTERVAL 48 HOUR
AND m.anchor_age+year(t0)-m.anchor_year>=18
AND u.careunit IN ('Medical Intensive Care Unit (MICU)',
'Medical/Surgical Intensive Care Unit (MICU/SICU)','Surgical Intensive Care Unit (SICU)',
'Trauma SICU (TSICU)','Coronary Care Unit (CCU)',
'Cardiac Vascular Intensive Care Unit (CVICU)','Neuro Surgical Intensive Care Unit (Neuro SICU)')''')
save(con,'eligibility_infection',f'''SELECT b.decision_id,
max(a.event_time) latest_abx_time,max(a.available_time) latest_abx_available,
bool_or(a.abx_source='icu_input') abx_icu_input_24h,
bool_or(a.abx_source='emar') abx_emar_24h
FROM {pq('bolus_decisions')} b JOIN {pq('antibiotic_administrations')} a
ON b.subject_id=a.subject_id AND b.hadm_id=a.hadm_id
AND a.event_time>=b.t0-INTERVAL 24 HOUR AND a.event_time<b.t0 AND a.available_time<b.t0
GROUP BY b.decision_id''')
save(con,'eligibility_culture',f'''SELECT b.decision_id,max(c.event_time) latest_culture_time
FROM {pq('bolus_decisions')} b JOIN {pq('blood_culture_collection')} c
ON b.subject_id=c.subject_id AND (b.hadm_id=c.hadm_id OR c.hadm_id IS NULL)
AND c.event_time>=b.t0-INTERVAL 24 HOUR AND c.event_time<b.t0
AND c.event_time>=coalesce(least(b.admittime,b.edregtime),b.admittime)
GROUP BY b.decision_id''')
save(con,'eligibility_bp',f'''SELECT b.decision_id,
min(x.x) FILTER(WHERE x.variable='map') map_min_2h,
min(x.x) FILTER(WHERE x.variable='sbp') sbp_min_2h,
count(*) bp_observations_2h,max(x.available_time) bp_latest_available
FROM {pq('bolus_decisions')} b JOIN {pq('vitals_clean')} x
ON b.stay_id=x.stay_id AND x.variable IN ('map','sbp')
AND x.charttime>=b.t0-INTERVAL 2 HOUR AND x.charttime<b.t0 AND x.available_time<b.t0
GROUP BY b.decision_id''')
save(con,'eligibility_pressor',f'''SELECT b.decision_id,
count(DISTINCT i.itemid) active_pressor_drugs,max(i.storetime) pressor_latest_recorded
FROM {pq('bolus_decisions')} b JOIN {pq('drug_inputs')} i
ON b.stay_id=i.stay_id AND i.starttime<b.t0 AND i.endtime>b.t0 AND i.storetime<b.t0
JOIN {pq('input_drug_map')} m USING(itemid)
WHERE m.vasopressor AND i.rate>0 AND i.statusdescription IS DISTINCT FROM 'Rewritten'
GROUP BY b.decision_id''')
save(con,'decision_eligibility',f'''SELECT b.*,a.* EXCLUDE(decision_id),c.* EXCLUDE(decision_id),
p.* EXCLUDE(decision_id),v.* EXCLUDE(decision_id),
a.latest_abx_time IS NOT NULL AND c.latest_culture_time IS NOT NULL suspected_infection,
coalesce(p.map_min_2h<65,false) OR coalesce(p.sbp_min_2h<90,false) hypotension_2h,
coalesce(p.map_min_2h<65,false) OR coalesce(p.sbp_min_2h<90,false) OR coalesce(v.active_pressor_drugs,0)>0 hemodynamic_instability
FROM {pq('bolus_decisions')} b
LEFT JOIN {pq('eligibility_infection')} a USING(decision_id)
LEFT JOIN {pq('eligibility_culture')} c USING(decision_id)
LEFT JOIN {pq('eligibility_bp')} p USING(decision_id)
LEFT JOIN {pq('eligibility_pressor')} v USING(decision_id)''')
# Choose first clinically eligible decision BEFORE removing ambiguous treatments.
# An ambiguous first decision does not permit choosing a later more convenient A.
save(con,'primary_index_all',f'''SELECT * FROM {pq('decision_eligibility')}
WHERE hours_since_icu>=6 AND suspected_infection AND hemodynamic_instability
QUALIFY row_number() OVER(PARTITION BY subject_id ORDER BY t0,stay_id,decision_id)=1''')
save(con,'primary_index',f'''SELECT * FROM {pq('primary_index_all')} WHERE A IS NOT NULL''')
summary={}
criteria={
'any_bolus_0_48h':'true',
'suspected_infection_0_48h':'suspected_infection',
'infection_and_instability_0_48h':'suspected_infection AND hemodynamic_instability',
'any_bolus_6_48h':'hours_since_icu>=6',
'suspected_infection_6_48h':'hours_since_icu>=6 AND suspected_infection',
'infection_and_instability_6_48h':'hours_since_icu>=6 AND suspected_infection AND hemodynamic_instability',
'infection_and_hypotension_6_48h':'hours_since_icu>=6 AND suspected_infection AND hypotension_2h'
}
for name,where in criteria.items():
    summary[name]=con.execute(f'''SELECT count(*) n,count(*) FILTER(WHERE A=1) lr,
    count(*) FILTER(WHERE A=0) saline,count(*) FILTER(WHERE A IS NULL) ambiguous
    FROM (SELECT * FROM {pq('decision_eligibility')} WHERE {where}
    QUALIFY row_number() OVER(PARTITION BY subject_id ORDER BY t0,stay_id,decision_id)=1)''').fetchdf().to_dict('records')[0]
summary['primary_units']=con.execute(f'''SELECT first_careunit,count(*) n,avg(A) lr_fraction
FROM {pq('primary_index')} GROUP BY first_careunit ORDER BY n DESC''').fetchdf().to_dict('records')
summary['primary_timing']=con.execute(f'''SELECT min(hours_since_icu) min_hours,
median(hours_since_icu) median_hours,max(hours_since_icu) max_hours,
avg(abx_icu_input_24h::INTEGER) antibiotic_icu_source_fraction,
avg(abx_emar_24h::INTEGER) antibiotic_emar_source_fraction,
avg(hypotension_2h::INTEGER) hypotension_fraction
FROM {pq('primary_index')}''').fetchdf().to_dict('records')
(OUT/'clinical_eligibility_audit.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2),flush=True)
