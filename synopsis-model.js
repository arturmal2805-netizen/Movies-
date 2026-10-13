// Bounded, private synopsis classifier; mirrors scripts/synopsis_model.py.
import {fitMargin} from './taste-model.js?v=quality43';
const stop=new Set('а без более бы был была были было быть в вам вас весь во вот все всего всех вы где да даже для до его ее если есть еще же за здесь и из или им их к как ко когда кто ли либо мне может мы на надо наш не него нее нет ни них но ну о об один он она они оно от по под при про раз с со так такой там те тем то того тоже той только том ты у уже что чтобы это эта эти этот'.split(' '));
const suffixes='иями ями ами иями его ого ему ому ией иям ием ею ия иью иях ие ые ое ей ий ый ой ем им ым ом их ых ую юю ая яя ов ев ий ы и я а е о у ю ь'.split(' ').sort((a,b)=>b.length-a.length);

export function synopsisTokens(film){
 const text=film.description||film.overview;if(typeof text!=='string')return [];
 const source=[...text.toLowerCase().replace(/ё/g,'е').slice(0,8000)].slice(0,4000).join(''),result=[];
 for(let word of source.match(/[a-zа-яё]{3,}/g)||[]){
  if(stop.has(word))continue;
  if(/[а-я]/.test(word))for(const suffix of suffixes)if(word.endsWith(suffix)&&word.length-suffix.length>=4){word=word.slice(0,-suffix.length);break;}
  result.push(word);if(result.length===160)break;
 }
 return result;
}

export function synopsisVector(words,vocabulary){
 const counts=new Map();for(const word of words)counts.set(word,(counts.get(word)||0)+1);
 const vector=[];for(const [word,idf] of vocabulary)if(counts.has(word))vector.push([`synopsis:${word}`,(1+Math.log(counts.get(word)))*idf,'synopsis']);
 const norm=Math.sqrt(vector.reduce((sum,[,value])=>sum+value*value,0));
 return norm?vector.map(([key,value,kind])=>[key,value/norm,kind]):[];
}

export function fitSynopsis(films,reactions){
 const documents=[];
 for(const film of films){const label=reactions[film.id]?.impression;if(label==='like'||label==='dislike')documents.push([synopsisTokens(film),label==='like']);}
 const empty={vocabulary:new Map(),weights:new Map(),bias:0,documentCount:0};
 const positive=documents.filter(([,label])=>label).length;
 if(documents.length<20||Math.min(positive,documents.length-positive)<3)return empty;
 const frequency=new Map(),occurrences=new Map();
 for(const [words] of documents){for(const word of new Set(words))frequency.set(word,(frequency.get(word)||0)+1);for(const word of words)occurrences.set(word,(occurrences.get(word)||0)+1);}
 const lexical=(a,b)=>a<b?-1:a>b?1:0;
 const words=[...frequency].filter(([,n])=>n>=3).map(([word])=>word).sort((a,b)=>occurrences.get(b)-occurrences.get(a)||lexical(a,b)).slice(0,128).sort(lexical);
 const vocabulary=new Map(words.map(word=>[word,Math.log((1+documents.length)/(1+frequency.get(word)))+1]));
 if(!vocabulary.size)return empty;
 const fitted=fitMargin(documents.map(([words,label])=>[synopsisVector(words,vocabulary),label]),240,.3);
 return {...fitted,vocabulary,documentCount:documents.filter(([words])=>words.length).length};
}

export function synopsisScore(film,model){
 const vector=synopsisVector(synopsisTokens(film),model?.vocabulary||new Map());if(!vector.length)return 0;
 return Math.max(-2,Math.min(2,model.bias+vector.reduce((sum,[key,value])=>sum+(model.weights.get(key)||0)*value,0)));
}
