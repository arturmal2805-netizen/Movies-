"""Small deterministic regularized classifier; no runtime ML dependencies."""
import math
from collections import Counter

MODEL_VERSION='linear-taste31'
SCALES={'genre':1,'category':.5,'keyword':1,'director':1,'language':.5,'period':.5}

def margin_features(vector):return {key:share*SCALES[key[0]] for key,share in vector.items()}

def fit_margin(examples,iterations=240):
 """Balanced logistic loss + L2 on coefficients and intercept (C=1).

 Drop features occurring in fewer than three distinct rated films. Accelerated
 full-batch gradient descent has a conservative Lipschitz step and fixed cap.
 """
 support=Counter(key for vector,_ in examples for key in vector)
 keys=sorted((key for key,count in support.items() if count>=3),key=lambda k:(k[0],str(k[1])))
 index={key:i for i,key in enumerate(keys)};positive=sum(label for _,label in examples);negative=len(examples)-positive
 if not positive or not negative:return {},0
 rows=[([(index[key],value) for key,value in vector.items() if key in index],label,.5/(positive if label else negative)) for vector,label in examples]
 ridge=1/len(rows);rate=1/(.25*max(1+sum(v*v for _,v in vector) for vector,_,_ in rows)+ridge)
 weights=[0.]*(len(keys)+1);look=weights[:];momentum=1.
 for _ in range(iterations):
  gradient=[ridge*w for w in look]
  for vector,label,mass in rows:
   z=look[-1]+sum(look[i]*value for i,value in vector)
   error=(1/(1+math.exp(-max(-35,min(35,z))))-label)*mass
   gradient[-1]+=error
   for i,value in vector:gradient[i]+=error*value
  updated=[w-rate*g for w,g in zip(look,gradient)]
  next_momentum=(1+math.sqrt(1+4*momentum*momentum))/2
  look=[v+(momentum-1)/next_momentum*(v-w) for v,w in zip(updated,weights)]
  weights=updated;momentum=next_momentum
 return dict(zip(keys,weights)),weights[-1]
