#!/usr/bin/env python
"""Segmentation by Hidden Markov Model."""
from __future__ import absolute_import, division, print_function
import logging

import numpy as np
import pandas as pd


def segment_hmm(cnarr, method, window=None):
    """Segment bins by Hidden Markov Model.

    Use Viterbi method to infer copy number segments from sequential data.

    With b-allele frequencies ('baf' column in `cnarr`), jointly segment
    log-ratios and b-allele frequencies across a chromosome.

    Parameters
    ----------
    cnarr : CopyNumArray
        The bin-level data to segment.
    method : string
        One of 'hmm' (3 states, flexible means), 'hmm-tumor' (5 states, flexible
        means), 'hmm-germline' (3 states, fixed means).

    Results
    -------
    segarr : CopyNumArray
        The segmented data.
    """
    # NB: Incorporate weights into smoothed log2 estimates
    # (Useful kludge until weighted HMM is in place)
    orig_log2 = cnarr['log2'].values.copy()
    cnarr['log2'] = cnarr.smoothed(window)

    logging.debug("Building model from observations")
    model = hmm_get_model(cnarr, method)
    logging.debug("Predicting states from model")
    obs = as_observation_matrix(cnarr)
    # A sequence of inferred discrete states. Length is the same as `freqs`,
    # with one state assigned to each input datapoint.
    states = model.predict(obs, lengths=chrom_arm_lengths(cnarr))

    # TODO logging.warn if model did not converge
    # print(model, end="\n\n")
    # print("Model params:\nmeans =", sorted(model.means_.flat))
    # print(model.monitor_, end="\n\n")

    # Merge adjacent bins with the same state to create segments
    from ..segfilters import squash_by_groups
    cnarr['log2'] = orig_log2
    cnarr['probes'] = 1
    segarr = squash_by_groups(cnarr, pd.Series(states), by_arm=True)
    return segarr


def hmm_get_model(cnarr, method):
    """

    Parameters
    ----------
    cnarr : CopyNumArray
        The normalized bin-level values to be segmented.
    method : string
        One of 'hmm', 'hmm-tumor', 'hmm-germline'

    Returns
    -------
    model :
        A hmmlearn Model trained on the given dataset.

    """
    # Delayed import so hmmlearn is an optional dependency
    from hmmlearn import hmm

    import warnings
    warnings.simplefilter('ignore', DeprecationWarning)
    warnings.simplefilter('ignore', RuntimeWarning)
    #  warnings.simplefilter('error', RuntimeWarning)

    assert method in ('hmm-tumor', 'hmm-germline', 'hmm')
    if method == 'hmm-tumor':
        state_means = np.column_stack([[-4, -1, 0, .585, 1]])
    else:
        state_means = np.column_stack([[-1, 0, .585]])
    kwargs = {
        'n_components': len(state_means),
        'means_prior': state_means,
        'means_weight': .5,
    }
    if method == 'hmm-germline':
        # Don't alter the state means when training the model
        kwargs.update({
            'init_params': 'stc',
            'params': 'stc',
        })
    model = hmm.GaussianHMM(covariance_type='diag', n_iter=100,
                            random_state=0xA5EED, **kwargs)
    if method == 'germline':
        model.means_ = state_means

    # Create observation matrix
    # TODO incorporate weights -- currently handled by smoothing
    # TODO incorporate inter-bin distances
    cnarr = cnarr.autosomes()
    freqs = as_observation_matrix(cnarr)

    if cnarr.chromosome.nunique() == 1:
        model.fit(freqs)
    else:
        model.fit(freqs, lengths=chrom_arm_lengths(cnarr))
    return model


def as_observation_matrix(cnarr):
    columns = [cnarr['log2'].values]
    if 'baf' in cnarr:
        # XXX untested
        columns.append(cnarr['baf'].values)
    return np.column_stack(columns)


def chrom_arm_lengths(cnarr):
    lengths = [len(x) for _, x in cnarr.by_arm()]
    assert sum(lengths) == len(cnarr)
    return lengths
