"""Fitted-law IPI curves and sharp mechanism-sensitivity regions."""
import numpy as np
import pandas as pd
from .sensitivity import endpoints, tilt

def make_curve(analysis,pred,nvars,delta_grid=None):
    if delta_grid is None:
        delta_grid=np.linspace(-np.log(4),np.log(4),81)
        delta_grid[np.abs(delta_grid)<1e-12]=0.
    p,mu0,mu1=pred.T
    assert np.isfinite(pred).all() and np.all((pred>=0)&(pred<=1))
    baseline=float(np.mean(mu0+(mu1-mu0)*p))
    rows=[]
    max_gap=0.
    max_excess=0.
    chis=np.linspace(0,1,101)
    for delta in delta_grid:
        for chi in chis:
            lo,center,hi,cert=endpoints(p,mu0,mu1,float(delta),float(chi))
            max_gap=max(max_gap,cert['dual_gap'])
            max_excess=max(max_excess,cert['budget_excess'])
            rows.append(dict(analysis=analysis,delta=delta,odds_multiplier=np.exp(delta),chi=chi,n=len(p),p=nvars,
                lower_risk=lo,ipi_risk=center,upper_risk=hi,
                lower_difference_pp=100*(lo-baseline),ipi_difference_pp=100*(center-baseline),upper_difference_pp=100*(hi-baseline),
                plugin_baseline_risk=baseline,ipi_lr_probability=float(np.mean(tilt(p,delta)))))
    df=pd.DataFrame(rows)
    lo=df.lower_risk.to_numpy().reshape(len(delta_grid),101)
    hi=df.upper_risk.to_numpy().reshape(len(delta_grid),101)
    cent=df.ipi_risk.to_numpy().reshape(len(delta_grid),101)
    assert np.all(np.diff(lo,axis=1)<=1e-12) and np.all(np.diff(hi,axis=1)>=-1e-12)
    assert np.allclose(lo[:,0],cent[:,0],atol=1e-12) and np.allclose(hi[:,0],cent[:,0],atol=1e-12)
    assert np.all(lo<=cent+1e-12) and np.all(cent<=hi+1e-12)
    assert np.all(lo[:,-1]<=baseline+1e-12) and np.all(hi[:,-1]>=baseline-1e-12)
    assert np.all((lo>=0)&(hi<=1))
    zero=df[np.isclose(df.delta,0)]
    assert np.max(np.abs(zero[['lower_difference_pp','ipi_difference_pp','upper_difference_pp']].to_numpy()))<1e-11
    assert max_gap<1e-11 and max_excess<1e-11
    return df,dict(analysis=analysis,n=len(p),p=nvars,plugin_baseline_risk=baseline,V=float(np.mean(p*(1-p))),
                   max_dual_gap=max_gap,max_budget_excess=max_excess,propensity_min=float(p.min()),propensity_max=float(p.max()))


