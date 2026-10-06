"""Independent finite-support LP checks and defining mathematical invariants."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
from scipy.optimize import linprog
from fluid_ici.analysis.sensitivity import tilt, allocate, endpoints


def global_lp(p, tau, delta, chi, maximize):
    # Include the optimizer's witness atoms, then verify with a separately
    # constructed LP over conditional masses and moment constraints.
    sign = (-1 if maximize else 1) * np.sign(delta)
    pp = p if delta > 0 else 1-p
    _, v, _ = allocate(pp, np.maximum(sign*tau, 0), abs(delta), chi)
    atoms = []
    for j in range(len(p)):
        b = p[j]+v[j]/p[j] if delta > 0 else p[j]-v[j]/(1-p[j])
        atoms.append(np.unique(np.clip(np.r_[np.linspace(0, 1, 201), p[j], b],0,1)))
    n, nvars = len(p), sum(map(len, atoms))
    eq = np.zeros((2*n, nvars))
    obj, var = np.empty(nvars), np.empty(nvars)
    start = 0
    for i, g in enumerate(atoms):
        sel = slice(start, start+len(g)); start += len(g)
        eq[2*i, sel], eq[2*i+1, sel] = 1, g
        obj[sel] = tau[i]*tilt(g, delta)/n
        var[sel] = (g-p[i])**2/n
    res = linprog(-obj if maximize else obj,
                  A_ub=var[None, :], b_ub=[chi*np.mean(p*(1-p))],
                  A_eq=eq, b_eq=np.column_stack([np.ones(n), p]).ravel(),
                  bounds=(0, None), method='highs')
    assert res.success, res.message
    return (-res.fun if maximize else res.fun)


def main():
    rng = np.random.default_rng(82617)
    p = np.r_[.02, .12, .35, .6, .83, .98]
    mu0 = rng.uniform(.2, .7, len(p))
    mu1 = np.clip(mu0+np.array([-.18,.25,-.05,.1,-.2,.1]), 0, 1)
    tau = mu1-mu0
    errors=[]
    for delta in [-1.38629436112,-.01,.01,.69314718056,1.38629436112]:
        previous=None
        for chi in [0,.001,.01,.1,.5,1]:
            lo, center, hi, cert = endpoints(p,mu0,mu1,delta,chi)
            assert lo <= center+1e-13 <= hi+1e-13
            assert cert['dual_gap'] < 1e-12 and cert['budget_excess'] < 1e-12
            if previous: assert lo <= previous[0]+1e-12 and hi >= previous[1]-1e-12
            previous=(lo,hi)
            if chi==0: assert lo==center==hi
            if chi==1:
                shift=tau*(p-tilt(p,delta))
                assert np.allclose([lo,hi],[center+np.minimum(shift,0).mean(),
                                           center+np.maximum(shift,0).mean()],atol=1e-13)
            for maximize in [False,True]:
                lp=mu0.mean()+global_lp(p,tau,delta,chi,maximize)
                error=abs(lp-(hi if maximize else lo)); errors.append(error)
                assert error < 2e-8, (delta,chi,maximize,error)
    for chi in [0,.5,1]:
        lo,center,hi,_=endpoints(p,mu0,mu1,0,chi)
        assert lo==center==hi
    # Deterministic treatment strata cannot change under any finite tilt.
    for delta in [-2,2]:
        lo,c,hi,_=endpoints([0,1],[.2,.3],[.4,.8],delta,1)
        assert lo==c==hi
    # Treatment relabeling symmetry, including both effect signs.
    for delta in [-1,.7]:
        for chi in [.02,.8]:
            a=endpoints(p,mu0,mu1,delta,chi)[:3]
            b=endpoints(1-p,mu1,mu0,-delta,chi)[:3]
            assert np.allclose(a,b,atol=1e-13)
    result={'independent_lp_comparisons':len(errors),'maximum_lp_error':max(errors),
            'nesting_zero_one_limits_relabeling_deterministic_strata':'passed'}
    print(json.dumps(result,indent=2))
    return result

class TestSensitivity(unittest.TestCase):
    def test_sharp_bounds_against_independent_linear_programs(self):
        result = main()
        self.assertEqual(result["independent_lp_comparisons"], 60)
        self.assertLess(result["maximum_lp_error"], 2e-8)

if __name__ == "__main__":
    unittest.main()

