import test from 'node:test';
import assert from 'node:assert/strict';
import {kyivTime,recentRecommendations} from './time.js';
test('Kyiv uses local calendar and automatic winter/summer offset',()=>{
 assert.equal(kyivTime('2026-01-15T23:30:00Z'), '16.01.2026, 01:30');
 assert.equal(kyivTime('2026-07-15T23:30:00Z'), '16.07.2026, 02:30');
});
test('hourly recommendations count server additions once and exclude manual saves, old and future rows',()=>{
 const now=Date.parse('2026-10-09T12:00:00Z');
 const rows=[{tmdb_id:1,reason:'match',created_at:'2026-10-09T11:00:01Z'},
 {tmdb_id:1,reason:'match',created_at:'2026-10-09T11:30:00Z'},
 {tmdb_id:2,reason:'match',created_at:'2026-10-09T11:00:00Z'},
 {tmdb_id:3,reason:null,created_at:'2026-10-09T11:50:00Z'},
 {tmdb_id:4,reason:'match',created_at:'2026-10-09T12:01:00Z'},
 {tmdb_id:5,reason:'match',created_at:'invalid'}];
 assert.deepEqual(recentRecommendations(rows,now),{count:1,latest:Date.parse('2026-10-09T11:30:00Z')});
 assert.equal(recentRecommendations(rows,now+3600000).count,1);
 assert.deepEqual(recentRecommendations([],now),{count:0,latest:null});
});
