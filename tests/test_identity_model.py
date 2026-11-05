"""Learned identity decisions preserve contextual evidence and ambiguity gates."""
import unittest

import numpy as np

from hiresense.graph.identity_model import IdentityScorer,IDENTITY_FEATURES


class IdentityModelTests(unittest.TestCase):
    def model(self):
        return {'version':'contextual-identity-logistic-v1','features':list(IDENTITY_FEATURES),
            'powers':np.eye(len(IDENTITY_FEATURES),dtype=int).tolist(),
            'mean':[0.]*len(IDENTITY_FEATURES),'scale':[1.]*len(IDENTITY_FEATURES),
            'weights':[0.]*len(IDENTITY_FEATURES),'intercept':10.,
            'logit_threshold':5.,'margin_threshold':1.}

    def test_even_a_high_model_score_cannot_merge_without_independent_context(self):
        scorer=IdentityScorer(self.model());x=np.ones((1,len(IDENTITY_FEATURES)))
        self.assertIsNone(scorer.choose([1],x,np.array([False]))[0])
        self.assertEqual(scorer.choose([1],x,np.array([True]))[0],1)

    def test_ambiguous_identical_scores_abstain_and_bad_schema_fails_closed(self):
        model=self.model();scorer=IdentityScorer(model)
        self.assertEqual(scorer.choose([1,2],np.ones((2,len(IDENTITY_FEATURES))),np.array([True,True]))[2],'ambiguous')
        model['scale'][0]=0
        with self.assertRaisesRegex(ValueError,'Invalid'):IdentityScorer(model)
