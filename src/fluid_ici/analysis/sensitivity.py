"""Sharp empirical plug-in endpoints for the manuscript, Appendix B (9)-(10).

This is for ONE binary treatment decision, not a longitudinal extension.
The global budget is E var(G|W) <= chi * E[p(1-p)]. No sampling CIs.

For m>1 and f(g)=m*g/(1+(m-1)*g), the minimum expectation at mean p
and variance v is m*p/(1+(m-1)*(p+v/p)), attained on {0,p+v/p}.
Writing b=p+v/p, a quadratic minorant L(g)=a*g+c*g*g has
 a=m*(1+2*(m-1)*b)/(1+(m-1)*b)**2,
 c=-m*(m-1)/(1+(m-1)*b)**2, and
 f(g)-L(g)=m*(m-1)**2*g*(g-b)**2/((1+(m-1)*g)*(1+(m-1)*b)**2).
This proves the conditional optimum without discretizing latent probabilities.
For negative delta use f_m(g)=1-f_(1/m)(1-g). Endpoint-specific positive
weights select the CATE sign where heterogeneity moves the target that way.
The resulting separable concave resource allocation is solved by a scalar
Lagrange multiplier, with attainable primal solutions and a dual certificate.
"""
import numpy as np
from scipy.special import expit, logit


def tilt(p, delta):
    p = np.asarray(p, dtype=float)
    with np.errstate(divide='ignore'):
        return expit(logit(p) + delta)


def allocate(p, weights, delta_abs, chi):
    """Maximum weighted displacement; empirical mean over all input rows."""
    p, weights = np.asarray(p, float), np.asarray(weights, float)
    if not 0 <= chi <= 1 or delta_abs < 0:
        raise ValueError('chi must be in [0,1], delta_abs must be nonnegative')
    if p.ndim != 1 or p.shape != weights.shape or not len(p):
        raise ValueError('Nonempty paired vectors required')
    if not np.isfinite(p).all() or not np.isfinite(weights).all():
        raise ValueError('Nonfinite inputs')
    if np.any((p < 0) | (p > 1) | (weights < 0)):
        raise ValueError('Invalid probabilities or weights')
    n = len(p)
    cap_all = p * (1 - p)
    budget = float(chi * cap_all.sum())
    active = (cap_all > 0) & (weights > 0)
    variance = np.zeros_like(p)
    if delta_abs == 0 or budget == 0 or not active.any():
        return 0., variance, {'dual_gap': 0., 'budget_excess': 0., 'lambda': 0.}
    pp, w, cap = p[active], weights[active], cap_all[active]
    k = np.expm1(delta_abs)
    m = 1 + k
    a = 1 + k * pp

    def objective(v):
        return w * (m * k * v) / (a * (a + k * v / pp))

    if budget >= cap.sum():
        v, lam = cap, 0.
    else:
        low, high = 0., float(np.max(w * m * k / (a * a)))
        for _ in range(60):
            lam = (low + high) / 2
            v = np.clip(pp / k * (np.sqrt(w * m * k / lam) - a), 0, cap)
            if v.sum() > budget:
                low = lam
            else:
                high = lam
        # Upper bracket is feasible; no rescaling of the conditional means.
        lam = high
        v = np.clip(pp / k * (np.sqrt(w * m * k / lam) - a), 0, cap)
    value = float(objective(v).sum() / n)
    variance[active] = v
    # Each v maximizes w*d(v)-lambda*v, so this certifies global optimality.
    dual = float((objective(v).sum() + lam * (budget - v.sum())) / n)
    return value, variance, {'dual_gap': dual - value,
                            'budget_excess': float((v.sum() - budget) / n),
                            'lambda': float(lam)}


def endpoints(p, mu0, mu1, delta, chi):
    p, mu0, mu1 = (np.asarray(v, float) for v in (p, mu0, mu1))
    if p.shape != mu0.shape or p.shape != mu1.shape:
        raise ValueError('Prediction arrays differ')
    if not np.isfinite(mu0).all() or not np.isfinite(mu1).all():
        raise ValueError('Nonfinite outcome regressions')
    tau = mu1 - mu0
    center = float(np.mean(mu0 + tau * tilt(p, delta)))
    if delta == 0:
        return center, center, center, {'dual_gap': 0., 'budget_excess': 0.}
    s = np.sign(delta)
    pp = p if delta > 0 else 1 - p
    down, _, d1 = allocate(pp, np.maximum(s * tau, 0), abs(delta), chi)
    up, _, d2 = allocate(pp, np.maximum(-s * tau, 0), abs(delta), chi)
    return center - down, center, center + up, {
        'dual_gap': max(d1['dual_gap'], d2['dual_gap']),
        'budget_excess': max(d1['budget_excess'], d2['budget_excess'])}
