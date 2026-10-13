"""Public-first ordering and frozen audience priors; never eligibility thresholds."""
import math
from production_policy import POLICY,style_affinity

SELECTION_VERSION='audience-first51'

def public_quality_tier(movie):
    rating=movie.get('rating',movie.get('vote_average'))
    remote=movie.get('remoteMetrics');remote=remote if isinstance(remote,dict) else {}
    votes=movie.get('vote_count');votes=remote.get('voteCount') if votes is None else votes
    if type(rating) not in (int,float) or not math.isfinite(rating) or not 0<rating<=10 or type(votes) not in (int,float) or not math.isfinite(votes) or votes<=0:return 0
    estimate=6+(rating-6)*(votes/(votes+500))
    return 2 if estimate>=6.25 else 1 if estimate>=5.5 else 0

def audience_production_score(movie,legacy=False,style_model=None):
    remote=movie.get('remoteMetrics');remote=remote if isinstance(remote,dict) else {}
    score=0 if legacy else 6*style_affinity(movie,style_model)
    for field,remote_field,weight in (('popularity','popularity',POLICY['popularity_weight']),('vote_count','voteCount',POLICY['votes_weight'])):
        raw=movie.get(field)
        if raw is None:raw=remote.get(remote_field)
        if type(raw) in (int,float) and math.isfinite(raw) and raw>0:score+=weight*math.log2(1+raw)
    return score

def audience_first_score(movie):
    """First sorting key, not a cutoff: trending reach plus audience breadth."""
    remote=movie.get('remoteMetrics')
    remote=remote if isinstance(remote,dict) else {}
    popularity=movie.get('popularity')
    votes=movie.get('vote_count')
    if popularity is None:popularity=remote.get('popularity')
    if votes is None:votes=remote.get('voteCount')
    score=0
    for value,weight in ((popularity,3),(votes,1)):
        if type(value) in (int,float) and math.isfinite(value) and value>0:
            score+=weight*math.log2(1+value)
    return score

def audience_score(movie,legacy=False):
    remote=movie.get('remoteMetrics')
    remote=remote if isinstance(remote,dict) else {}
    popularity=movie.get('popularity')
    votes=movie.get('vote_count')
    if popularity is None:popularity=remote.get('popularity')
    if votes is None:votes=remote.get('voteCount')
    score=0
    if type(popularity) in (int,float) and math.isfinite(popularity) and popularity>0:
        score=(.4 if legacy else 1.6)*max(-2,min(2,math.log2((popularity+1)/9)))
    # Vote count expresses audience breadth, separately from today's trending
    # popularity. Missing/zero counts supply no evidence rather than a penalty.
    if type(votes) in (int,float) and math.isfinite(votes) and votes>0:
        score+=(.1 if legacy else .7)*max(-1,min(3,math.log2((votes+500)/1500)))
    return score

def public_quality_score(movie,predictive=False,legacy=False):
    rating=movie.get('rating')
    if rating is None:rating=movie.get('vote_average')
    remote=movie.get('remoteMetrics')
    remote=remote if isinstance(remote,dict) else {}
    votes=movie.get('vote_count')
    if votes is None:votes=remote.get('voteCount')
    if type(rating) not in (int,float) or not math.isfinite(rating) or not 0<rating<=10:return 0
    if type(votes) not in (int,float) or not math.isfinite(votes) or votes<=0:return 0
    quality=6.5+(rating-6.5)*(votes/(votes+500))
    return (quality-6.5)*((.006 if legacy else .2) if predictive else .08)

def audience_priority_score(movie,predictive=False,legacy=False):
    # Known audiences should matter more than weak keyword coincidences.
    # Cap the public component so large personal differences still dominate.
    value=audience_score(movie,legacy)+public_quality_score(movie,predictive,legacy)
    return value if legacy else max(-3,min(3,value))


def confidence_quality(movie):
    rating=movie.get('rating',movie.get('vote_average'))
    remote=movie.get('remoteMetrics');remote=remote if isinstance(remote,dict) else {}
    votes=movie.get('vote_count');votes=remote.get('voteCount') if votes is None else votes
    if type(rating) not in (int,float) or not math.isfinite(rating) or not 0<rating<=10 or type(votes) not in (int,float) or not math.isfinite(votes) or votes<=0:return 5.
    return 5+(rating-5)*(votes/(votes+300))

def selection_priority_score(movie,personal=0.,style_model=None):
    # Continuous ordering: personal evidence must affect every comparison,
    # rather than a tie that almost never occurs. It never vetoes a candidate.
    fit=7*math.tanh(personal/3) if type(personal) in (int,float) and math.isfinite(personal) else 0.
    return audience_production_score(movie,legacy=True)+12*(confidence_quality(movie)-6)+fit+6*style_affinity(movie,style_model)
