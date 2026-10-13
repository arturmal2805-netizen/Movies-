import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeInterests,buildStyleModel,patternAffinity} from './interests.js';
import {ServerStore} from './server.js';
import {buildSelectionProfile,selectionScore,selectionPriorityScore} from './audience-priority.js';
test('known director aliases are deduplicated and malformed names ignored',()=>{assert.equal(normalizeInterests({directors:['Robert Eggers','Роберт Эггерс',{name:{}},'Coralie Fargeat']}).directors.length,2);});
test('live ranking rewards reference themes across directors without a name bonus',()=>{
 const films=[{id:1,director:'Robert Eggers',keywords:['gothic horror','period piece']},...Array.from({length:20},(_,i)=>({id:i+2,keywords:['vampire','zombie']}))];
 const reactions=Object.fromEntries(films.map(f=>[f.id,{impression:f.id===1?'like':'dislike'}]));
 const profile=buildSelectionProfile(films,reactions),base={popularity:10,vote_count:1000,productionBudget:5000000};
 const similar={...base,director:'Someone else',keywords:['gothic horror','period piece']},bare={...base,director:'Robert Eggers',keywords:[]};
 assert.ok(selectionScore(similar,profile)>selectionScore(bare,profile));
 const cleared=buildSelectionProfile(films,reactions,{directors:[]});assert.equal(selectionPriorityScore(similar,0,cleared.styleModel),selectionPriorityScore(bare,0,cleared.styleModel));
});
test('explicit empty directors and reordered genres persist as preferences',()=>{assert.deepEqual(normalizeInterests({directors:[],genrePriority:['dystopian','bad']}).directors,[]);assert.equal(normalizeInterests({genrePriority:['dystopian']}).genrePriority[0],'dystopian');assert.equal(normalizeInterests().directors.length,5);});
test('positive reference patterns target other directors and never copy the favorite name',()=>{
 const films=[{id:1,director:'Robert Eggers',keywords:['gothic horror','period piece','vampire']},...Array.from({length:20},(_,i)=>({id:i+2,director:'Other',keywords:['vampire','zombie']}))],reactions=Object.fromEntries(films.map(f=>[f.id,{impression:f.id===1?'like':'dislike'}]));
 const model=buildStyleModel(films,reactions);
 assert.ok(patternAffinity({director:'Other',keywords:['gothic horror','period piece']},model)>0);assert.equal(patternAffinity({director:'Robert Eggers',keywords:[]},model),0);assert.equal(patternAffinity({keywords:['vampire','zombie']},model),0);
 assert.equal(buildStyleModel(films,reactions,{directors:[]}).referenceCount,0);
});
test('cloud save updates only owned preference metadata and confirms the returned value',async()=>{
 const memory=new Map();globalThis.localStorage={setItem:(k,v)=>memory.set(k,v),getItem:k=>memory.get(k),removeItem:k=>memory.delete(k)};globalThis.sessionStorage={removeItem:()=>{}};
 let sent;const store=new ServerStore({url:'https://example.com',publishableKey:'public'},async(url,options)=>{sent={url,options};return new Response(JSON.stringify({id:'owner',user_metadata:{other_field:'untouched',nightshift_interests:JSON.parse(options.body).data.nightshift_interests}}));});
 store.session={user:{id:'owner'},access_token:'token',expires_at:Date.now()/1000+3600};
 const pref=normalizeInterests({directors:[],genrePriority:['dystopian','horror']});assert.deepEqual(await store.saveInterests(pref),pref);assert.equal(sent.options.method,'PUT');assert.ok(sent.url.endsWith('/auth/v1/user'));assert.deepEqual(Object.keys(JSON.parse(sent.options.body)),['data']);assert.deepEqual(Object.keys(JSON.parse(sent.options.body).data),['nightshift_interests']);
});
test('unconfirmed or wrong-account preference saves are never reported as successful',async()=>{
 for(const user of [{id:'owner'},{id:'other',user_metadata:{nightshift_interests:normalizeInterests()}}]){const store=new ServerStore({url:'https://example.com',publishableKey:'public'},async()=>new Response(JSON.stringify(user)));store.session={user:{id:'owner'},access_token:'token',expires_at:Date.now()/1000+3600};await assert.rejects(store.saveInterests(normalizeInterests()),/не подтвердил/);}
});

test('patterns must retain a coherent combination from one liked example',()=>{
 const films=[{id:1,director:'Robert Eggers',keywords:['gothic horror','period piece']},{id:2,director:'Zach Cregger',keywords:['body horror','identity']}];
 const model=buildStyleModel(films,{1:{impression:'like'},2:{impression:'like'}});
 assert.equal(patternAffinity({keywords:['period piece','identity']},model),0);assert.ok(patternAffinity({keywords:['gothic horror','period piece']},model)>0);
});


test('cinematic concepts generalize synonyms and do not reward duplicate labels',()=>{
 const model=buildStyleModel([{id:1,director:'Robert Eggers',keywords:['gothic horror','period piece','isolation']}],{1:{impression:'like'}});
 assert.ok(patternAffinity({keywords:['gothic','19th century','alone']},model)>0);
 assert.equal(patternAffinity({keywords:['gothic','gothic horror']},model),0);
 assert.equal(patternAffinity({keywords:['school','beach','friends']},model),0);
});
