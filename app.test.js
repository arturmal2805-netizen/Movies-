import test from 'node:test';
import assert from 'node:assert/strict';
import { films, selectFilms } from './app.js';
test('filters combine mood, duration and genre',()=>{assert.deepEqual(selectFilms({mood:'cozy',genre:'Комедия',duration:100}).map(f=>f.id),[2]);assert.equal(selectFilms({mood:'thrill',duration:100}).length,0);});
test('search accepts Russian, original title and director',()=>{assert.equal(selectFilms({query:'  АМЕЛИ  '})[0].id,8);assert.equal(selectFilms({query:'arrival'})[0].id,7);assert.deepEqual(selectFilms({query:'Вильнёв'}).map(f=>f.id),[3,7]);});
test('saved films respect the other filters',()=>{assert.deepEqual(selectFilms({savedOnly:true,saved:[1,8],mood:'romance'}).map(f=>f.id),[8]);assert.equal(selectFilms({savedOnly:true}).length,0);});
test('catalog has unique IDs and usable metadata',()=>{assert.equal(new Set(films.map(f=>f.id)).size,films.length);for(const f of films){assert.ok(f.description&&f.original&&f.moods.length);assert.ok(f.minutes>0&&f.rating>0&&f.rating<=10);}});
