"""Shared, bounded public-audience prior; never an eligibility threshold."""
import math

SELECTION_VERSION='audience-priority45'

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
