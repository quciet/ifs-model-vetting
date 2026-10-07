"""Descriptive run diagnostics; no causal or pass/fail judgments."""
import math
import numpy as np

CORE_VARIABLES = frozenset('GDPPCP POP GDP EDYRS25 EDYRS15 LIFEXPECT CBR CDR MIGRANTS SFPARDEE INFMOR XS CARANN YL AGP CLPCP GINIDOM INFRAELECACC ENP ENDEM GOVCORRUPT THREATREC'.split())


def lane_for(variable, dims):
    if variable in CORE_VARIABLES:
        return 'Core'
    return 'Dyadic' if dims.count(1) > 1 else 'Other'


def trajectory_metrics(years, baseline, comparison, atol=0., rtol=0.):
    """sMAPE is 0..200 percent; both-zero observations contribute zero.

    Correlation is undefined for constant series. Sign flips are changes in the
    sign of the between-run difference, ignoring within-tolerance points. Gaps
    in valid annual observations break the crossing sequence.
    """
    order = np.argsort(years)
    years, baseline, comparison = np.asarray(years)[order], np.asarray(baseline)[order], np.asarray(comparison)[order]
    finite = np.isfinite(baseline) & np.isfinite(comparison)
    x, y = baseline[finite], comparison[finite]
    delta = y - x
    denominator = np.abs(x) + np.abs(y)
    symmetric = np.zeros(len(x))
    np.divide(200. * np.abs(delta), denominator, out=symmetric, where=denominator != 0)
    correlation = None
    if len(x)>1 and np.std(x)>0 and np.std(y)>0:
        correlation = float(np.corrcoef(x,y)[0,1])
    # Do not infer crossings across missing years or invalid values.
    flips, previous, previous_year = 0, None, None
    for year, a, b in zip(years, baseline, comparison):
        if previous_year is not None and year != previous_year + 1:
            previous = None
        previous_year = year
        if not (math.isfinite(a) and math.isfinite(b)):
            previous = None
            continue
        difference = b-a
        if abs(difference) <= atol+rtol*abs(a):
            continue
        sign = 1 if difference>0 else -1
        if previous is not None and previous != sign:
            flips += 1
        previous = sign
    changed = np.abs(delta) > atol+rtol*np.abs(x)
    peak = int(np.argmax(np.abs(delta))) if len(delta) and np.any(delta != 0) else None
    return {'mean_smape':float(np.mean(symmetric)) if len(x) else None,
            'sse':float(np.dot(delta,delta)) if len(x) else None,
            'pearson_r':correlation, 'sign_flips':flips,
            'cumulative_abs_delta':float(np.sum(np.abs(delta))) if len(x) else None,
            'max_divergence_year':int(years[finite][peak]) if peak is not None else None,
            'first_divergence_year':int(years[finite][changed][0]) if changed.any() else None,
            'finite_years':len(x), 'nonfinite_years':int((~finite).sum()),
            'both_zero_years':int((denominator==0).sum()),
            'zero_baseline_changed_years':int(((x==0)&(y!=0)).sum())}


def audit_slices(variable, dims, buckets, keys, baseline, comparison, atol, rtol):
    """One row per sector/partner slice; choose its country by cumulative |delta|.

    The first region axis is the country under review. All remaining non-time
    axes define fixed slices. A bilateral slice therefore fixes the partner,
    while selecting the origin country with the largest cumulative difference.
    Actual coordinate keys are retained for direct chart navigation.
    """
    if not dims or dims[0]!=0 or not len(keys):
        return []
    cohort_keys, inverse = np.unique(keys[:,1:], axis=0, return_inverse=True)
    finite = np.isfinite(baseline)&np.isfinite(comparison)
    magnitude = np.where(finite, np.abs(comparison-baseline), 0.)
    scores = np.bincount(inverse, weights=magnitude, minlength=len(cohort_keys))
    counts = np.bincount(inverse, weights=finite.astype(int), minlength=len(cohort_keys))
    region_axis = dims[1:].index(1) if 1 in dims[1:] else None
    slice_axes = [i for i in range(len(dims)-1) if i!=region_axis]
    slices = {}
    for index, coordinate in enumerate(cohort_keys):
        identity = tuple(int(coordinate[i]) for i in slice_axes)
        previous = slices.get(identity)
        if previous is None or (counts[index]>0, scores[index]) > (counts[previous]>0, scores[previous]):
            slices[identity] = index
    # Group rows once, rather than scanning a million-row payload per partner.
    order = np.argsort(inverse, kind='stable')
    boundaries = np.concatenate(([0],np.cumsum(np.bincount(inverse,minlength=len(cohort_keys)))))
    result = []
    for identity,index in slices.items():
        rows = order[boundaries[index]:boundaries[index+1]]
        coordinate = cohort_keys[index]
        labels = [buckets[dim][int(key)] for dim,key in zip(dims[1:],coordinate)]
        slice_labels = [labels[i] for i in slice_axes]
        tracked = variable + (' ['+' / '.join(slice_labels)+']' if slice_labels else '')
        cohort = ' / '.join(labels) if labels else 'Global series'
        result.append({'base_variable':variable, 'tracked_variable':tracked,
                       'lane':lane_for(variable,dims), 'worst_cohort':cohort,
                       'selectors':coordinate.tolist(), 'slice_keys':list(identity),
                       **trajectory_metrics(keys[rows,0],baseline[rows],comparison[rows],atol,rtol)})
    return result


LEDGER_FIELDS = ['base_variable','tracked_variable','lane','worst_cohort','mean_smape','sse',
                 'pearson_r','sign_flips','cumulative_abs_delta','first_divergence_year',
                 'max_divergence_year','finite_years','nonfinite_years','both_zero_years',
                 'zero_baseline_changed_years','selectors']
