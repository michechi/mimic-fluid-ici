"""Stage clinically relevant observations, preserving event and recording times.

This script does not create outcomes or use post-bolus observations for baseline.
Time restrictions are imposed explicitly by the downstream cohort builder.
"""
import json,re,sys
from .settings import *
from .definitions import antibiotic_regex

con=connect()
counts={}
_save=save
def save(con,name,query):
    if '--resume' in sys.argv and (WORK/(name+'.parquet')).exists():
        n=con.execute(f'SELECT count(*) FROM {pq(name)}').fetchone()[0]
        print(f'{name}: reusing {n:,} staged rows',flush=True)
        return n
    return _save(con,name,query)
con.execute(f'CREATE VIEW icu_subject AS SELECT DISTINCT subject_id FROM {pq("meta")}')
abx_regex=antibiotic_regex()
counts['input_drug_map']=save(con,'input_drug_map',f'''SELECT itemid,label,
regexp_matches(lower(label),{sqlstr(abx_regex)}) AND NOT regexp_matches(lower(label),'irrigant') antibiotic,
itemid IN (221289,221662,221749,221906,222315,229617,229630,229631,229632) vasopressor,
itemid=221653 dobutamine,
regexp_matches(lower(label),'hydrocortisone|solu.cortef') hydrocortisone
FROM {pq('d_items')} WHERE linksto='inputevents' AND (
regexp_matches(lower(label),{sqlstr(abx_regex)}) OR
itemid IN (221289,221662,221749,221906,222315,229617,229630,229631,229632,221653)
OR regexp_matches(lower(label),'hydrocortisone|solu.cortef')) AND NOT regexp_matches(lower(label),'irrigant')''')
counts['drug_inputs']=save(con,'drug_inputs',f'''SELECT subject_id::BIGINT subject_id,hadm_id::BIGINT hadm_id,
stay_id::BIGINT stay_id,itemid::INTEGER itemid,starttime::TIMESTAMP starttime,endtime::TIMESTAMP endtime,
storetime::TIMESTAMP storetime,amount::DOUBLE amount,amountuom,rate::DOUBLE rate,rateuom,
patientweight::DOUBLE patientweight,orderid::BIGINT orderid,linkorderid::BIGINT linkorderid,
ordercategoryname,ordercomponenttypedescription,statusdescription
FROM {raw('icu/inputevents')} WHERE itemid::INTEGER IN (SELECT itemid FROM {pq('input_drug_map')})''')
if '--drugs-only' in sys.argv:
    print('Updated drug staging only.',flush=True)
    sys.exit(0)
labs=[50802,50804,50806,50809,50811,50813,50820,50821,50822,50824,
50861,50862,50863,50868,50878,50882,50885,50893,50902,50912,50931,50971,50983,51006,
51221,51222,51237,51265,51275,51301]
counts['labs']=save(con,'labs',f'''SELECT labevent_id::BIGINT labevent_id,subject_id::BIGINT subject_id,
hadm_id::BIGINT hadm_id,specimen_id::BIGINT specimen_id,itemid::INTEGER itemid,
charttime::TIMESTAMP charttime,storetime::TIMESTAMP storetime,valuenum::DOUBLE valuenum,valueuom
FROM {raw('hosp/labevents')}
WHERE itemid::INTEGER IN ({','.join(map(str,labs))}) AND valuenum IS NOT NULL
AND subject_id::BIGINT IN (SELECT subject_id FROM icu_subject)''')
charts=[220045,220050,220051,220052,220179,220180,220181,225309,225310,225312,
220210,224690,220277,223761,223762,225664,220621,226537,220739,223900,223901,
226512,224639,223835,226732,223848,223849,229314,224700,223834,
225965,226499,224154,225183,227438,224191,225806,225807,228004,228005,228006,
224144,224145,224153,226457,227290,225126]
counts['charts']=save(con,'charts',f'''SELECT subject_id::BIGINT subject_id,hadm_id::BIGINT hadm_id,
stay_id::BIGINT stay_id,itemid::INTEGER itemid,charttime::TIMESTAMP charttime,
storetime::TIMESTAMP storetime,value,valuenum::DOUBLE valuenum,valueuom
FROM {raw('icu/chartevents')} WHERE itemid::INTEGER IN ({','.join(map(str,charts))})''')
uo=[226559,226560,226561,226584,226563,226564,226565,226567,226557,226558,227488,227489]
counts['urine']=save(con,'urine',f'''SELECT subject_id::BIGINT subject_id,hadm_id::BIGINT hadm_id,
stay_id::BIGINT stay_id,itemid::INTEGER itemid,charttime::TIMESTAMP charttime,
storetime::TIMESTAMP storetime,value::DOUBLE volume,valueuom,
CASE WHEN itemid::INTEGER=227488 AND value::DOUBLE>0 THEN -value::DOUBLE ELSE value::DOUBLE END urine_ml
FROM {raw('icu/outputevents')} WHERE itemid::INTEGER IN ({','.join(map(str,uo))})''')
counts['procedures_support']=save(con,'procedures_support',f'''SELECT subject_id::BIGINT subject_id,
hadm_id::BIGINT hadm_id,stay_id::BIGINT stay_id,itemid::INTEGER itemid,starttime::TIMESTAMP starttime,
endtime::TIMESTAMP endtime,storetime::TIMESTAMP storetime,value::DOUBLE AS value,valueuom,
orderid::BIGINT orderid,statusdescription
FROM {raw('icu/procedureevents')}
WHERE itemid::INTEGER IN (225441,225802,225803,225805,225809,225955,225792,225794)''')
summary={'rows':counts,
 'lab_items':con.execute(f'SELECT itemid,label,fluid FROM {pq("d_labitems")} WHERE itemid IN ({",".join(map(str,labs))})').fetchdf().to_dict('records'),
 'chart_items':con.execute(f'SELECT itemid,label,unitname FROM {pq("d_items")} WHERE itemid IN ({",".join(map(str,charts))})').fetchdf().to_dict('records'),
 'medication_items':con.execute(f'SELECT * FROM {pq("input_drug_map")}').fetchdf().to_dict('records')}
(OUT/'clinical_stage_profile.json').write_text(json.dumps(summary,indent=2))
print('Clinical observations staged; no outcomes summarized.',flush=True)
