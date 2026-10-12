"""Bounded private synopsis model; no external AI service or fitted public weights."""
import math
import re
from collections import Counter
from taste_model import fit_margin

STOP=set('а без более бы был была были было быть в вам вас весь во вот все всего всех вы где да даже для до его ее если есть еще же за здесь и из или им их к как ко когда кто ли либо мне может мы на надо наш не него нее нет ни них но ну о об один он она они оно от по под при про раз с со так такой там те тем то того тоже той только том ты у уже что чтобы это эта эти этот'.split())
SUFFIX=sorted('иями ями ами иями его ого ему ому ией иям ием ею ия иью иях ие ые ое ей ий ый ой ем им ым ом их ых ую юю ая яя ов ев ий ы и я а е о у ю ь'.split(),key=len,reverse=True)


def synopsis_tokens(movie):
    text=movie.get('description') or movie.get('overview')
    if not isinstance(text,str):return []
    result=[]
    for word in re.findall('[a-zа-яё]{3,}',text.lower().replace('ё','е')[:4000]):
        if word in STOP:continue
        if re.search('[а-я]',word):
            for suffix in SUFFIX:
                if word.endswith(suffix) and len(word)-len(suffix)>=4:
                    word=word[:-len(suffix)];break
        result.append(word)
    return result[:160]


def synopsis_vector(words,vocabulary):
    counts=Counter(words)
    values={('synopsis',word):(1+math.log(counts[word]))*idf
            for word,idf in vocabulary.items() if counts[word]}
    length=math.sqrt(sum(value*value for value in values.values()))
    return {key:value/length for key,value in values.items()} if length else {}


def fit_synopsis(ratings):
    rows=[row for row in ratings if row.get('impression') in ('like','dislike')]
    documents=[(synopsis_tokens(row.get('metadata') or {}),row['impression']=='like') for row in rows]
    empty={'vocabulary':{},'weights':{},'bias':0.,'document_count':0}
    positive=sum(label for _,label in documents)
    if len(documents)<20 or min(positive,len(documents)-positive)<3:return empty
    frequency=Counter();occurrences=Counter()
    for words,_ in documents:
        frequency.update(set(words));occurrences.update(words)
    # Vocabulary uses only training documents. A synopsis cannot create its own
    # word weights at prediction time. Stable ordering is shared with the browser.
    words=sorted((word for word,count in frequency.items() if count>=3),
                 key=lambda word:(-occurrences[word],word))[:128]
    vocabulary={word:math.log((1+len(documents))/(1+frequency[word]))+1 for word in sorted(words)}
    if not vocabulary:return empty
    examples=[(synopsis_vector(words,vocabulary),label) for words,label in documents]
    weights,bias=fit_margin(examples,regularization=.3)
    return {'vocabulary':vocabulary,'weights':weights,'bias':bias,
            'document_count':sum(bool(words) for words,_ in documents)}


def synopsis_score(movie,model):
    vector=synopsis_vector(synopsis_tokens(movie),model.get('vocabulary',{}))
    # Missing/unrecognised text provides no evidence, never a dislike signal.
    if not vector:return 0.
    margin=model['bias']+sum(model['weights'].get(key,0)*value for key,value in vector.items())
    return max(-2.,min(2.,margin))
