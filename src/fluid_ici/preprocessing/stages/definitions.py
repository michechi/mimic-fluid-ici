"""Explicit adaptations of pinned MIMIC concepts for this baseline study."""
import re
from .settings import REF

# Generic names absent from the pinned prescription concept; recorded explicitly
# so the adaptation can be reviewed and reproduced. Routes are checked separately.
ANTIBIOTIC_ADDITIONS = ['daptomycin','ertapenem','imipenem','doripenem',
 'tigecycline','polymyxin','colistin','fosfomycin','ceftolozane','avibactam']
def antibiotic_terms():
    base=re.findall(r"LOWER\(drug\) LIKE '%([^']+)%' THEN 1",(REF/'medication__antibiotic.sql').read_text())
    assert len(base)>100
    return sorted(set(base+ANTIBIOTIC_ADDITIONS))
def antibiotic_regex():
    return '|'.join(re.escape(x) for x in antibiotic_terms())

SYSTEMIC_ROUTES = ['IV','IV DRIP','IV BOLUS','IV INFUSION','PB','IM',
 'PO','PO/NG','ORAL','NG','ND','J TUBE','G TUBE']
