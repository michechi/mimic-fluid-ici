"""Nested cross-fitting with fold-contained preprocessing and stacking."""
import os
os.environ.setdefault('OMP_NUM_THREADS','2')
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
os.environ.setdefault('VECLIB_MAXIMUM_THREADS','2')
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.base import BaseEstimator,TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder,StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import log_loss,roc_auc_score,brier_score_loss
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits

THREADS = 2

NAMES=['ridge','boost7','boost15']

class ContinuousClipper(BaseEstimator,TransformerMixin):
    """Training-only tail clipping; leave binary and low-cardinality fields intact."""
    def fit(self,X,y=None):
        X=np.asarray(X,dtype=float)
        self.lo_=np.full(X.shape[1],-np.inf);self.hi_=np.full(X.shape[1],np.inf)
        for j in range(X.shape[1]):
            if len(np.unique(X[:,j]))>20:
                self.lo_[j],self.hi_[j]=np.quantile(X[:,j],[.005,.995])
        return self
    def transform(self,X):return np.clip(np.asarray(X,dtype=float),self.lo_,self.hi_)

def make_model(name,x,seed):
    cat=[c for c in x if x[c].dtype==object]
    num=[c for c in x if c not in cat]
    num_steps=[('impute',SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True))]
    if name=='ridge':num_steps.extend([('clip',ContinuousClipper()),('scale',StandardScaler())])
    pre=ColumnTransformer([
      ('num',Pipeline(num_steps),num),
      ('cat',Pipeline([('impute',SimpleImputer(strategy='constant',fill_value='__MISSING__')),
        ('encode',OneHotEncoder(handle_unknown='infrequent_if_exist',min_frequency=10,sparse_output=False))]),cat)
    ],sparse_threshold=0)
    if name=='ridge':
        model=LogisticRegression(C=.1,solver='lbfgs',max_iter=2000,tol=1e-5)
    else:
        model=HistGradientBoostingClassifier(max_iter=250,learning_rate=.05,
          max_leaf_nodes=7 if name=='boost7' else 15,min_samples_leaf=40,
          l2_regularization=5,early_stopping=False,random_state=seed)
    return Pipeline([('preprocess',pre),('model',model)])

def fitted_predictions(name,xtrain,ytrain,xeval,seed):
    with warnings.catch_warnings(record=True) as records,threadpool_limits(limits=THREADS):
        warnings.simplefilter('always',ConvergenceWarning)
        model=make_model(name,xtrain,seed).fit(xtrain,ytrain)
        pred=model.predict_proba(xeval)[:,1]
        failures=[str(w.message) for w in records if issubclass(w.category,ConvergenceWarning)]
    if failures:raise RuntimeError('Model convergence failed: '+'; '.join(failures))
    assert np.isfinite(pred).all() and ((pred>=0)&(pred<=1)).all()
    return pred

def fit_stack(xtrain,ytrain,xeval,seed):
    ytrain=np.asarray(ytrain,dtype=int)
    cv=StratifiedKFold(n_splits=3,shuffle=True,random_state=seed)
    inner=np.full((len(xtrain),len(NAMES)),np.nan)
    full=np.empty((len(xeval),len(NAMES)))
    splits=list(cv.split(xtrain,ytrain))
    for k,name in enumerate(NAMES):
        for j,(tr,va) in enumerate(splits):
            assert not np.intersect1d(tr,va).size
            inner[va,k]=fitted_predictions(name,xtrain.iloc[tr],ytrain[tr],xtrain.iloc[va],seed+100*k+j)
        full[:,k]=fitted_predictions(name,xtrain,ytrain,xeval,seed+100*k+9)
    assert np.isfinite(inner).all()
    def loss(w):return log_loss(ytrain,np.clip(inner@w,1e-12,1-1e-12))
    opt=minimize(loss,np.ones(len(NAMES))/len(NAMES),method='SLSQP',bounds=[(0,1)]*len(NAMES),
      constraints=[{'type':'eq','fun':lambda w:w.sum()-1}],options={'ftol':1e-10,'maxiter':300})
    if not opt.success:raise RuntimeError('Stacking optimization failed: '+opt.message)
    weights=np.clip(opt.x,0,1);weights/=weights.sum()
    return full@weights,full,weights,[log_loss(ytrain,inner[:,k]) for k in range(len(NAMES))]

