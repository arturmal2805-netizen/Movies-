import test from 'node:test';
import assert from 'node:assert/strict';
import {filmCategories,categoryOptions} from './categories.js';

test('category list contains the six focus categories and reset',()=>{
 assert.deepEqual(categoryOptions.slice(1).map(c=>c[2]),['Horror','Creature Horror','Dystopian Movies','Psychological Horror','Body Horror','Folk Horror']);
});
test('older films retain known overlapping horror subgenres',()=>{
 assert.deepEqual(filmCategories({tmdbId:1091}),['horror','creature-horror','body-horror']);
 assert.deepEqual(filmCategories({tmdbId:530385}),['horror','psychological-horror','folklore-horror']);
});
test('keywords classify horror themes without treating monster comedy as horror',()=>{
 assert.deepEqual(filmCategories({genreIds:[27],keywords:['creature feature','body horror']}),['horror','creature-horror','body-horror']);
 assert.deepEqual(filmCategories({genreIds:[35],keywords:['giant monster']}),[]);
 assert.deepEqual(filmCategories({genreIds:[878],keywords:['dystopia']}),['dystopian']);
 assert.deepEqual(filmCategories({genreIds:[27],keywords:['psychological horror','folk horror']}),['horror','psychological-horror','folklore-horror']);
});
test('animation is not automatically anime and uncategorized films remain available',()=>{
 assert.deepEqual(filmCategories({genreIds:[16],originalLanguage:'en'}),[]);
 assert.deepEqual(filmCategories({genreIds:[16],originalLanguage:'ja'}),[]);
 assert.deepEqual(filmCategories({genreIds:[16],productionCountries:['JP']}),[]);
 assert.deepEqual(filmCategories({genreIds:[12,35]}),[]);
});

// Both runtimes must agree on the same annotated regression examples.
import {readFileSync} from 'node:fs';
import {categoryRules} from './category-rules.js';
const checks=JSON.parse(readFileSync(new URL('./config/category-checks.json',import.meta.url)));
test('generated browser rules match the server source of truth',()=>{
 assert.deepEqual(categoryRules,JSON.parse(readFileSync(new URL('./config/category-rules.json',import.meta.url))));
});
for(const check of checks)test(`category benchmark: ${check.name}`,()=>assert.deepEqual(filmCategories(check.movie),check.expected));

import {isEligibleForDiscovery} from './categories.js';
test('year boundary and mixed genre exceptions agree with server policy',()=>{
 for(const {name,movie,expected} of JSON.parse(readFileSync(new URL('./config/discovery-checks.json',import.meta.url))))assert.equal(isEligibleForDiscovery(movie),expected,name);
});
test('combined psychological evidence requires horror and both themes',()=>{
 assert.deepEqual(filmCategories({genreIds:[27],keywords:['paranoia','hallucination']}),['horror','psychological-horror']);
 assert.deepEqual(filmCategories({genreIds:[27],keywords:['paranoia']}),['horror']);
 assert.deepEqual(filmCategories({genreIds:[18],keywords:['paranoia','hallucination']}),[]);
});
