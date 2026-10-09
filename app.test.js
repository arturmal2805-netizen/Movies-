import test from 'node:test';
import assert from 'node:assert/strict';
import { films, selectFilms } from './app.js';
test('filters combine category, duration and genre',()=>{assert.deepEqual(selectFilms({mood:'comedy',genre:'Комедия',duration:100}).map(f=>f.id),[2]);assert.equal(selectFilms({mood:'creature-horror',duration:100}).length,0);});
test('search accepts Russian, original title and director',()=>{assert.equal(selectFilms({query:'  АМЕЛИ  '})[0].id,8);assert.equal(selectFilms({query:'arrival'})[0].id,7);assert.deepEqual(selectFilms({query:'Вильнёв'}).map(f=>f.id),[3,7]);});
test('saved films respect the other filters',()=>{assert.deepEqual(selectFilms({savedOnly:true,saved:[1,9],mood:'dystopian'}).map(f=>f.id),[9]);assert.equal(selectFilms({savedOnly:true}).length,0);});
test('catalog has unique IDs and usable metadata',()=>{assert.equal(new Set(films.map(f=>f.id)).size,films.length);for(const f of films){assert.ok(f.description&&f.original&&Array.isArray(f.moods));assert.ok(f.minutes>0&&f.rating>0&&f.rating<=10);}});
import {hasCompleteMetadata,sourceState} from './sources.js';
test('complete cards require every real metric including zero popularity',()=>{assert.equal(hasCompleteMetadata({poster:'poster.jpg',imdb:8,popularity:0}),true);assert.equal(hasCompleteMetadata({poster:'poster.jpg',popularity:20}),false);});
test('source reports stale success and disconnected providers',()=>{assert.equal(sourceState('tmdb',{sources:{tmdb:{status:'ok',lastSuccess:'2026-10-09T00:00:00Z'}}},Date.parse('2026-10-09T04:00:00Z')).status,'stale');assert.equal(sourceState('netflix',null).status,'not_connected');});
import {normalizeRating,ratingWeight,isArchived} from './ratings.js';
test('old ratings migrate without losing favorites or watched films',()=>{assert.deepEqual(normalizeRating('like'),{impression:'like'});assert.equal(isArchived('watched'),true);assert.equal(isArchived('like'),false);assert.equal(normalizeRating({cinematography:99,plot:'8'}),null);});
test('two scales and impression affect recommendation weight',()=>{assert.ok(ratingWeight({cinematography:9,plot:9,impression:'like'})>ratingWeight('like'));assert.ok(ratingWeight({cinematography:2,plot:2,impression:'dislike'})<ratingWeight('dislike'));assert.equal(ratingWeight({impression:'neutral'}),0);assert.equal(isArchived({impression:'neutral',ratedAt:'2026-10-09'}),true);});

test('Trakt connects only after server recommendations confirm its contribution',()=>{
 const now=Date.parse('2026-10-09T12:00:00Z');
 const row={reason:'recommendation',created_at:'2026-10-09T11:30:00Z',metadata:{discoverySources:['tmdb','trakt']}};
 assert.equal(sourceState('trakt',null,now,[]).status,'scheduled');
 assert.equal(sourceState('trakt',null,now,[row]).status,'ok');
 assert.equal(sourceState('trakt',null,now,[{...row,reason:null}]).status,'scheduled');
 assert.equal(sourceState('trakt',null,now,[{...row,created_at:'2026-10-10T00:00:00Z'}]).status,'scheduled');
 assert.equal(sourceState('trakt',null,now,[{...row,created_at:'2026-10-09T08:00:00Z'}]).status,'stale');
});

test('Trakt health response confirms connection even with an empty collection',()=>{
 const now=Date.parse('2026-10-09T12:00:00Z');
 assert.equal(sourceState('trakt',{sources:{trakt:{status:'ok',lastSuccess:'2026-10-09T11:55:00Z'}}},now,[]).status,'ok');
 const state=sourceState('trakt',{sources:{trakt:{status:'error',httpStatus:401,lastSuccess:'2026-10-09T11:55:00Z'}}},now,[]);
 assert.equal(state.status,'error');assert.ok(state.note.includes('HTTP 401'));
});
