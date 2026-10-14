"""Canonical public admission rules shared by source retrieval and final ranking."""
import datetime,math
from movie_features import eligible_for_discovery
from production_policy import production_exclusion

def valid_candidate(movie,minimum_votes,today,require_target=None,interests=None):
 if not isinstance(movie,dict) or type(movie.get('id')) is not int or movie['id']<=0:return False
 if movie.get('adult') or not movie.get('poster_path') or not eligible_for_discovery(movie,require_target=require_target) or production_exclusion(movie,interests=interests):return False
 try:
  released=datetime.date.fromisoformat(movie.get('release_date',''))
  count=float(movie.get('vote_count',0));rating=float(movie.get('vote_average',0));popularity=float(movie.get('popularity',0))
  return released<=today and count>=minimum_votes and 0<=rating<=10 and all(math.isfinite(v) for v in (count,rating,popularity))
 except (ValueError,TypeError):return False
