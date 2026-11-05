"""Portable contextual identity scorer with abstention calibrated on held-out records."""
import json
import math
from pathlib import Path

import numpy as np

from .resolution import AuthorMatcher, normalize_name

IDENTITY_FEATURES=('name','coauthor_fraction','log_shared_coauthors','venue_fraction','year_distance',
                   'coauthor_idf','log_name_aliases','log_history_years','log_history_venues','known_observed_coauthor_fraction')


def identity_features(matcher,record,candidates):
    observed={normalize_name(n) for n in record.get('observed_coauthors',())}
    rows=[];supported=[]
    for author in candidates:
        f=matcher.features(record,author);profile=matcher.profiles[author]
        shared=observed & profile['coauthors']
        rarity=sum(1/math.log2(2+len(matcher.coauthor_index.get(name,()))) for name in shared)
        aliases=len(matcher.names.get(' '.join(sorted(profile['name'].split())),()))
        rows.append([f['name'],f['coauthors'],math.log1p(len(shared)),f['venues'],f['years'],rarity,
                     math.log1p(aliases),math.log1p(len(profile['years'])),math.log1p(len(profile['venues'])),
                     sum(name in matcher.coauthor_index for name in observed)/max(1,len(observed))])
        supported.append(f['name']>=.7 and bool(shared))
    return np.asarray(rows,dtype=np.float64).reshape(-1,len(IDENTITY_FEATURES)),np.asarray(supported,dtype=bool)


class IdentityScorer:
    def __init__(self,model):
        if model['version']!='contextual-identity-logistic-v1' or tuple(model['features'])!=IDENTITY_FEATURES:
            raise ValueError('Identity model schema differs')
        self.model=model
        self.powers=np.asarray(model['powers'],dtype=np.int16)
        self.mean=np.asarray(model['mean'],dtype=np.float64)
        self.scale=np.asarray(model['scale'],dtype=np.float64)
        self.weights=np.asarray(model['weights'],dtype=np.float64)
        if self.powers.shape!=(len(self.weights),len(IDENTITY_FEATURES)) or self.mean.shape!=self.weights.shape or self.scale.shape!=self.weights.shape:
            raise ValueError('Identity model dimensions differ')
        if not all(np.isfinite(v).all() for v in (self.mean,self.scale,self.weights)) or (self.scale<=0).any() or (self.powers<0).any() or (self.powers.sum(axis=1)>2).any():
            raise ValueError('Invalid identity parameters')

    def logits(self,features):
        if not len(features):return np.empty(0)
        polynomial=np.prod(np.power(features[:,None,:],self.powers[None,:,:]),axis=2)
        return ((polynomial-self.mean)/self.scale) @ self.weights+float(self.model['intercept'])

    def choose(self,candidates,features,supported):
        values=self.logits(features)
        if not len(values):return None,0.,'unresolved',{}
        ids=np.asarray(candidates,dtype=np.int64)
        order=np.lexsort((ids,-values));best=int(order[0]);logit=float(values[best])
        margin=logit-float(values[order[1]]) if len(order)>1 else 100.
        score=1/(1+math.exp(-max(-40,min(40,logit))))
        features_out=dict(zip(IDENTITY_FEATURES,map(float,features[best])))
        features_out.update(margin=margin,logit=logit,score_scope='Class-weighted decision score, not a calibrated identity probability.')
        if not supported[best] or logit<float(self.model['logit_threshold']):return None,score,'unresolved',features_out
        if margin<float(self.model['margin_threshold']):return None,score,'ambiguous',features_out
        return int(ids[best]),score,'matched',features_out


class LearnedAuthorMatcher(AuthorMatcher):
    def __init__(self,database,model,max_candidates=128):
        super().__init__(database,max_candidates=max_candidates,year_mode='distance',policy='conservative')
        self.scorer=IdentityScorer(model)

    @classmethod
    def from_existing(cls,matcher,model):
        result=cls.__new__(cls);result.__dict__.update(matcher.__dict__)
        result.year_mode='distance';result.initial_blocks=True;result.scorer=IdentityScorer(model)
        return result

    def match(self,record,threshold=None,ambiguity_margin=None):
        candidates,available,skipped=self.candidates(record)
        features,supported=identity_features(self,record,candidates)
        author,score,decision,explanation=self.scorer.choose(candidates,features,supported)
        return author,score,decision,explanation,candidates,available,skipped
