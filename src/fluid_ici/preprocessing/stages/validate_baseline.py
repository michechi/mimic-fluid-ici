"""Independent integrity queries and small temporal-boundary regression checks."""
import json
from .settings import *
con=connect()
checks={}
checks['future_or_concurrent_vital_information_excluded']=con.execute('''
WITH records(event_time,store_time) AS (VALUES
(TIMESTAMP '2020-01-01 09:00:00',TIMESTAMP '2020-01-01 09:30:00'),
(TIMESTAMP '2020-01-01 09:00:00',TIMESTAMP '2020-01-01 10:00:00'),
(TIMESTAMP '2020-01-01 09:00:00',TIMESTAMP '2020-01-01 10:01:00'),
(TIMESTAMP '2020-01-01 10:00:00',TIMESTAMP '2020-01-01 09:00:00'))
SELECT count(*)=1 FROM records
WHERE event_time<TIMESTAMP '2020-01-01 10:00:00'
AND store_time<TIMESTAMP '2020-01-01 10:00:00' ''').fetchone()[0]
checks['ambiguous_first_decision_does_not_move_index']=con.execute('''
WITH decisions(person,t0,A) AS (VALUES(1,1,NULL),(1,2,1),(2,1,0)),
firsts AS (SELECT * FROM decisions QUALIFY row_number() OVER(PARTITION BY person ORDER BY t0)=1)
SELECT count(*)=1 AND min(person)=2 FROM firsts WHERE A IS NOT NULL''').fetchone()[0]
checks['unique_people_and_binary_A']=con.execute(f'''SELECT count(*)=count(DISTINCT subject_id)
AND count(*)=count(DISTINCT decision_id) AND count(*) FILTER(WHERE A NOT IN (0,1) OR A IS NULL)=0
FROM {pq('analysis_baseline')}''').fetchone()[0]
checks['all_index_times_inside_observation_window']=con.execute(f'''SELECT bool_and(t0>=intime+INTERVAL 6 HOUR
AND t0<intime+INTERVAL 48 HOUR AND t0<outtime) FROM {pq('primary_index')}''').fetchone()[0]
checks['all_index_events_have_prior_infection_and_instability']=con.execute(f'''SELECT bool_and(suspected_infection
AND hemodynamic_instability AND latest_abx_time<t0 AND latest_abx_available<t0 AND latest_culture_time<t0)
FROM {pq('primary_index')}''').fetchone()[0]
checks['no_earlier_eligible_decision_skipped']=con.execute(f'''SELECT count(*)=0
FROM {pq('primary_index_all')} p JOIN {pq('decision_eligibility')} e
ON p.subject_id=e.subject_id AND e.t0<p.t0
WHERE e.hours_since_icu>=6 AND e.suspected_infection AND e.hemodynamic_instability''').fetchone()[0]
checks['historical_diagnoses_are_from_earlier_completed_admissions']=con.execute(f'''SELECT count(*)=0
FROM {pq('primary_index')} p JOIN {pq('prior_hospitalizations')} h USING(decision_id)
WHERE h.hadm_id=p.hadm_id OR h.dischtime>=p.admittime''').fetchone()[0]
checks['no_ambiguous_decision_in_dataset']=con.execute(f'''SELECT count(*)=0 FROM {pq('analysis_baseline')} b
JOIN {pq('primary_index_all')} p USING(decision_id) WHERE p.index_fluid_types<>1''').fetchone()[0]
quality=json.loads((OUT/'baseline_quality.json').read_text())
checks['all_baseline_recording_times_precede_treatment']=not any(quality['pretreatment_timing_violations'].values())
checks['recorded_blood_pressure_in_prespecified_ranges']=con.execute(f'''SELECT bool_and(
(x_map_last_value IS NULL OR x_map_last_value BETWEEN 20 AND 200)
AND (x_sbp_last_value IS NULL OR x_sbp_last_value BETWEEN 40 AND 300)
AND (x_dbp_last_value IS NULL OR x_dbp_last_value BETWEEN 10 AND 180)) FROM {pq('analysis_baseline')}''').fetchone()[0]
assert all(checks.values()),checks
(OUT/'baseline_validation.json').write_text(json.dumps(checks,indent=2))
print(json.dumps(checks,indent=2),flush=True)
