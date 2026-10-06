"""Stage prescriptions, administration records and culture COLLECTION times."""
import json,re
from .settings import *
from .definitions import antibiotic_terms,antibiotic_regex

con=connect()
con.execute(f'CREATE VIEW icu_hadm AS SELECT DISTINCT hadm_id FROM {pq("meta")}')
con.execute(f'CREATE VIEW icu_subject AS SELECT DISTINCT subject_id FROM {pq("meta")}')
terms=antibiotic_terms()
abx_regex=antibiotic_regex()
fluid_regex=r'ringer|sodium chloride|saline|nacl|^ns$|^lr$'
counts={}
counts['prescriptions_icu']=save(con,'prescriptions_icu',f'''SELECT subject_id::BIGINT subject_id,hadm_id::BIGINT hadm_id,
pharmacy_id::BIGINT pharmacy_id,poe_id,starttime::TIMESTAMP starttime,stoptime::TIMESTAMP stoptime,
drug_type,drug,formulary_drug_cd,route,dose_val_rx,dose_unit_rx,prod_strength,
doses_per_24_hrs::DOUBLE doses_per_24_hrs,
regexp_matches(lower(drug),{sqlstr(abx_regex)}) AND coalesce(drug_type,'')<>'BASE'
AND coalesce(route,'') NOT IN ('OU','OS','OD','AU','AS','AD','TP')
AND NOT regexp_matches(lower(coalesce(route,'')),'ear|eye')
AND NOT regexp_matches(lower(drug),'cream|desensitization|ophth oint|gel') abx_intent,
regexp_matches(lower(drug),{sqlstr(fluid_regex)}) fluid_name_candidate,
regexp_matches(lower(drug),'hydrocortisone|solu.cortef') hydrocortisone_name
FROM {raw('hosp/prescriptions')}
WHERE hadm_id::BIGINT IN (SELECT hadm_id FROM icu_hadm)''')
counts['emar_subjects']=save(con,'emar_subjects',f'''SELECT subject_id::BIGINT subject_id,hadm_id::BIGINT hadm_id,
emar_id,emar_seq::BIGINT emar_seq,poe_id,pharmacy_id::BIGINT pharmacy_id,
charttime::TIMESTAMP charttime,storetime::TIMESTAMP storetime,medication,event_txt,
regexp_matches(lower(coalesce(medication,'')),{sqlstr(abx_regex)}) abx_name,
regexp_matches(lower(coalesce(medication,'')),{sqlstr(fluid_regex)}) fluid_name_candidate,
regexp_matches(lower(coalesce(medication,'')),'hydrocortisone|solu.cortef') hydrocortisone_name
FROM {raw('hosp/emar')}
WHERE subject_id::BIGINT IN (SELECT subject_id FROM icu_subject)''')
counts['emar_target_ids']=save(con,'emar_target_ids',f'''SELECT DISTINCT emar_id FROM {pq('emar_subjects')}
WHERE abx_name OR fluid_name_candidate OR hydrocortisone_name''')
counts['emar_target_detail']=save(con,'emar_target_detail',f'''SELECT subject_id::BIGINT subject_id,emar_id,
emar_seq::BIGINT emar_seq,parent_field_ordinal,administration_type,pharmacy_id::BIGINT pharmacy_id,
complete_dose_not_given,dose_due,dose_due_unit,dose_given,dose_given_unit,
product_amount_given,product_unit,product_code,product_description,
prior_infusion_rate,infusion_rate,infusion_rate_unit,route,infusion_complete,
new_iv_bag_hung,continued_infusion_in_other_location
FROM {raw('hosp/emar_detail')}
WHERE emar_id IN (SELECT emar_id FROM {pq('emar_target_ids')})''')
# No organism results are used to define baseline suspected infection.
counts['culture_events']=save(con,'culture_events',f'''SELECT DISTINCT subject_id::BIGINT subject_id,
hadm_id::BIGINT hadm_id,micro_specimen_id::BIGINT micro_specimen_id,
charttime::TIMESTAMP charttime,chartdate::DATE chartdate,spec_itemid::INTEGER spec_itemid,
spec_type_desc,test_itemid::INTEGER test_itemid,test_name
FROM {raw('hosp/microbiologyevents')}
WHERE subject_id::BIGINT IN (SELECT subject_id FROM icu_subject)''')
summary={'rows':counts,'antimicrobial_terms':terms}
queries={
'fluid_emar_names':f'''SELECT medication,event_txt,count(*) n FROM {pq('emar_subjects')} WHERE fluid_name_candidate GROUP BY medication,event_txt ORDER BY n DESC LIMIT 60''',
'fluid_prescription_names':f'''SELECT drug,drug_type,route,count(*) n FROM {pq('prescriptions_icu')} WHERE fluid_name_candidate GROUP BY drug,drug_type,route ORDER BY n DESC LIMIT 50''',
'fluid_detail_patterns':f'''SELECT d.administration_type,d.route,d.dose_given_unit,d.product_unit,d.infusion_rate_unit,d.new_iv_bag_hung,d.complete_dose_not_given,count(*) n,
count(try_cast(d.dose_given AS DOUBLE)) numeric_dose,count(try_cast(d.product_amount_given AS DOUBLE)) numeric_product
FROM {pq('emar_target_detail')} d JOIN {pq('emar_subjects')} e USING(emar_id)
WHERE e.fluid_name_candidate GROUP BY ALL ORDER BY n DESC LIMIT 40''',
'culture_names':f'''SELECT spec_type_desc,test_name,count(DISTINCT micro_specimen_id) n FROM {pq('culture_events')} GROUP BY ALL ORDER BY n DESC LIMIT 40''',
'emar_hadm_missing':f'''SELECT count(*) n,count(*) FILTER (WHERE hadm_id IS NULL) hadm_missing,count(*) FILTER(WHERE hadm_id IN (SELECT hadm_id FROM icu_hadm)) known_icu_hospitalization FROM {pq('emar_subjects')}''',
'abx_emar_status':f'''SELECT event_txt,count(*) n FROM {pq('emar_subjects')} WHERE abx_name GROUP BY event_txt ORDER BY n DESC''',
}
for name,query in queries.items():
    summary[name]=con.execute(query).fetchdf().to_dict('records')
(OUT/'medication_stage_profile.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2),flush=True)
