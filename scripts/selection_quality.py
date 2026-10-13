"""Read-only comparison against the former gate; production uses ranked batches."""
from movie_features import profile, match_score, rejection_score, eligible_for_discovery
from statistics import median
from audience_priority import audience_score,public_quality_score


def chronological(rows):
    return sorted((r for r in rows if r.get('impression') in ('like', 'dislike')),
                  key=lambda r: (str(r.get('updated_at') or ''), r.get('tmdb_id', 0)))


def selection_floor(rows,include_quality=True):
    decisive = chronological(rows)
    if len(decisive) < 100 or not all(r.get('updated_at') for r in decisive):
        return None
    split = int(len(decisive) * .8)
    model = profile(decisive[:split],include_quality=include_quality)
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
    previous = model
    previous_floor = None
    def measure(selected_model,cutoff,legacy_gate,include_audience=False):
        predictions = [(match_score(r['metadata'], selected_model)+(audience_score(r['metadata'])+public_quality_score(r['metadata'],selected_model.predictive) if include_audience else 0), rejection_score(r['metadata'], selected_model), r['impression'] == 'like') for r in test]
        ordered=sorted(predictions,key=lambda p:p[0],reverse=True)
        pool=[item for item in ordered if not legacy_gate or item[1]>=-.8 and (cutoff is None or item[0]>=cutoff)]
        kept=pool[:30]
        liked=sum(label for _,_,label in kept)
        return {'accepted': len(kept), 'liked': liked, 'precision': liked / len(kept) if kept else None,
                'eligible_pool':len(pool),'likes_at_10': sum(label for _,_,label in kept[:10])}
    return {'status': 'evaluated', 'training': len(train), 'tested': len(test),
            'positives': sum(r['impression']=='like' for r in test),
            'floor': previous_floor,'metric':'top_30', 'before': measure(previous,previous_floor,False), 'after': measure(model,None,False,True)}
