"""Calibrate admission on earlier feedback, never on the candidate being judged."""
from movie_features import profile, match_score, rejection_score, eligible_for_discovery
from statistics import median


def chronological(rows):
    return sorted((r for r in rows if r.get('impression') in ('like', 'dislike')),
                  key=lambda r: (str(r.get('updated_at') or ''), r.get('tmdb_id', 0)))


def selection_floor(rows):
    decisive = chronological(rows)
    if len(decisive) < 100 or not all(r.get('updated_at') for r in decisive):
        return None
    split = int(len(decisive) * .8)
    model = profile(decisive[:split])
    validation = [r for r in decisive[split:] if eligible_for_discovery(r.get('metadata') or {})]
    positives = [match_score(r['metadata'], model) for r in validation if r['impression'] == 'like']
    if not model.predictive or len(validation) < 20 or len(positives) < 2:
        return None
    scores = sorted(match_score(r['metadata'], model) for r in validation)
    # Retain the strongest 15% rather than almost the entire negative-heavy
    # pool, but do not set the threshold above the median positive example.
    return min(scores[int((len(scores) - 1) * .85)], median(positives))


def selection_evaluation(rows):
    decisive = chronological(rows)
    if len(decisive) < 100 or not all(r.get('updated_at') for r in decisive):
        return {'status': 'insufficient'}
    split = int(len(decisive) * .8)
    train, test = decisive[:split], decisive[split:]
    test = [r for r in test if eligible_for_discovery(r.get('metadata') or {})]
    model = profile(train)
    floor = selection_floor(train)
    predictions = [(match_score(r['metadata'], model), rejection_score(r['metadata'], model), r['impression'] == 'like') for r in test]
    def measure(calibrated):
        kept = [label for score, margin, label in predictions if margin >= -.8 and (not calibrated or floor is None or score >= floor)]
        return {'accepted': len(kept), 'liked': sum(kept), 'precision': sum(kept) / len(kept) if kept else None}
    return {'status': 'evaluated', 'training': len(train), 'tested': len(test),
            'positives': sum(label for _, _, label in predictions),
            'floor': floor, 'before': measure(False), 'after': measure(True)}
