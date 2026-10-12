"""Calendar-year coverage anchored to the baseline run."""
import numpy as np


def year_map(buckets):
    mapping = {int(key): int(str(label).strip()) for key, label in buckets.get(0, {}).items()}
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('Duplicate calendar years in metadata')
    return mapping


def periods(years):
    years = sorted(set(map(int, years)))
    result = []
    for year in years:
        if result and year == result[-1][1] + 1:
            result[-1][1] = year
        else:
            result.append([year, year])
    return result


def coverage(baseline, comparison):
    anchor, other = set(year_map(baseline).values()), set(year_map(comparison).values())
    return {'baseline_years': sorted(anchor), 'compared_years': sorted(anchor & other),
            'missing_years': sorted(anchor - other), 'excluded_years': sorted(other - anchor),
            'baseline_periods': periods(anchor), 'compared_periods': periods(anchor & other),
            'missing_periods': periods(anchor - other), 'excluded_periods': periods(other - anchor)}


def anchored_payload(payload, dims, own_buckets, baseline_buckets):
    for axis, dim in enumerate(dims):
        unknown = set(map(int, np.unique(payload['keys'][:, axis]))) - own_buckets[dim].keys()
        if unknown:
            raise ValueError(f'Unmapped coordinates on dimension {dim}: {sorted(unknown)[:10]}')
    if 0 not in dims:
        return payload
    result = payload.copy()
    mapping = year_map(own_buckets)
    anchor = set(year_map(baseline_buckets).values())
    for axis, dim in enumerate(dims):
        if dim == 0:
            result['keys'][:, axis] = [mapping[int(key)] for key in result['keys'][:, axis]]
            result = result[np.isin(result['keys'][:, axis], list(anchor))]
    return result
