"""Stage core metadata and relevant fluid records; no outcomes are selected."""
import json
from .settings import *

con=connect()
counts={}
counts['patients']=save(con,'patients',f'''SELECT subject_id::BIGINT subject_id, gender,
anchor_age::INTEGER anchor_age, anchor_year::INTEGER anchor_year, anchor_year_group
FROM {raw('hosp/patients')}''')
counts['admissions']=save(con,'admissions',f'''SELECT subject_id::BIGINT subject_id, hadm_id::BIGINT hadm_id,
admittime::TIMESTAMP admittime, admission_type, admission_location, race,
edregtime::TIMESTAMP edregtime, edouttime::TIMESTAMP edouttime
FROM {raw('hosp/admissions')}''')
counts['icustays']=save(con,'icustays',f'''SELECT subject_id::BIGINT subject_id, hadm_id::BIGINT hadm_id,
stay_id::BIGINT stay_id, intime::TIMESTAMP intime, outtime::TIMESTAMP outtime,
first_careunit, last_careunit FROM {raw('icu/icustays')}''')
counts['meta']=save(con,'meta',f'''SELECT s.*,p.* EXCLUDE(subject_id),a.* EXCLUDE(subject_id,hadm_id)
FROM {pq('icustays')} s JOIN {pq('patients')} p USING(subject_id)
JOIN {pq('admissions')} a USING(subject_id,hadm_id)''')
assert counts['meta']==counts['icustays']==94458
con.execute(f'CREATE VIEW icu_hadm AS SELECT DISTINCT hadm_id FROM {pq("meta")}')
con.execute(f'CREATE VIEW icu_subject AS SELECT DISTINCT subject_id FROM {pq("meta")}')
counts['transfers']=save(con,'transfers',f'''SELECT subject_id::BIGINT subject_id,hadm_id::BIGINT hadm_id,
transfer_id::BIGINT transfer_id,eventtype,careunit,intime::TIMESTAMP intime,outtime::TIMESTAMP outtime
FROM {raw('hosp/transfers')} WHERE hadm_id::BIGINT IN (SELECT hadm_id FROM icu_hadm)''')
counts['d_items']=save(con,'d_items',f'SELECT * REPLACE(itemid::INTEGER AS itemid) FROM {raw("icu/d_items")}')
counts['d_labitems']=save(con,'d_labitems',f'SELECT * REPLACE(itemid::INTEGER AS itemid) FROM {raw("hosp/d_labitems")}')
counts['fluid_inputs']=save(con,'fluid_inputs',f'''SELECT subject_id::BIGINT subject_id,hadm_id::BIGINT hadm_id,
stay_id::BIGINT stay_id,starttime::TIMESTAMP starttime,endtime::TIMESTAMP endtime,storetime::TIMESTAMP storetime,
itemid::INTEGER itemid,amount::DOUBLE amount,amountuom,rate::DOUBLE rate,rateuom,
orderid::BIGINT orderid,linkorderid::BIGINT linkorderid,ordercategoryname,
secondaryordercategoryname,ordercomponenttypedescription,ordercategorydescription,
patientweight::DOUBLE patientweight,totalamount::DOUBLE totalamount,totalamountuom,statusdescription,
originalamount::DOUBLE originalamount,originalrate::DOUBLE originalrate,
CASE WHEN amountuom='mL' THEN amount::DOUBLE WHEN amountuom='L' THEN amount::DOUBLE*1000 END ml
FROM {raw('icu/inputevents')}
WHERE itemid::INTEGER IN (225158,225828,220953,220954,220955,220956,226361,226363,226364,226375)''')
counts['boluses']=save(con,'boluses',f'''SELECT f.*,m.intime,m.outtime,
CASE WHEN f.itemid=225828 THEN 1 ELSE 0 END A
FROM {pq('fluid_inputs')} f JOIN {pq('meta')} m USING(subject_id,hadm_id,stay_id)
WHERE f.itemid IN (225158,225828) AND f.ordercategoryname='03-IV Fluid Bolus'
AND f.ordercomponenttypedescription='Main order parameter' AND f.ordercategorydescription='Bolus'
AND f.statusdescription IS DISTINCT FROM 'Rewritten' AND f.ml>0
AND f.endtime>=f.starttime AND f.starttime>=m.intime AND f.starttime<m.outtime''')
assert counts['boluses']==156619
counts['first_stay_bolus']=save(con,'first_stay_bolus',f'''WITH first AS (
SELECT stay_id,min(starttime) t0 FROM {pq('boluses')} GROUP BY stay_id
), decision AS (
SELECT b.stay_id,f.t0,count(*) n_records,count(DISTINCT itemid) n_fluids,
CASE WHEN count(DISTINCT itemid)=1 THEN max(A) END A,sum(ml) recorded_index_ml
FROM {pq('boluses')} b JOIN first f ON b.stay_id=f.stay_id AND b.starttime=f.t0 GROUP BY b.stay_id,f.t0
) SELECT d.*,m.* EXCLUDE(stay_id),
epoch(d.t0-m.intime)/3600 hours_since_icu,
epoch(d.t0-m.admittime)/3600 hours_since_hospital,
(m.anchor_age+year(d.t0)-m.anchor_year)::INTEGER age_approx,
m.anchor_age=91 age_topcoded,
(CAST(substr(m.anchor_year_group,1,4) AS INTEGER)+year(d.t0)-m.anchor_year)::INTEGER calendar_year_low
FROM decision d JOIN {pq('meta')} m USING(stay_id)''')
assert counts['first_stay_bolus']==38370
counts['services']=save(con,'services',f'''SELECT subject_id::BIGINT subject_id,hadm_id::BIGINT hadm_id,
transfertime::TIMESTAMP transfertime,prev_service,curr_service FROM {raw('hosp/services')}
WHERE hadm_id::BIGINT IN (SELECT hadm_id FROM icu_hadm)''')
(OUT/'core_stage_counts.json').write_text(json.dumps(counts,indent=2))
print('Core source counts verified.',flush=True)
