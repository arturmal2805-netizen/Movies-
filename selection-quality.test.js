import test from 'node:test';
import assert from 'node:assert/strict';
import {ratingSummary,selectionFloor,evaluateSelection} from './selection-quality.js';

test('quality separates actual recommendations, other ratings and neutral feedback',()=>{
 const row=(id,impression,mode)=>({tmdb_id:id,impression,metadata:{recommendationMode:mode}});
 const result=ratingSummary([row(1,'like','manual'),row(2,'dislike','scheduled'),row(3,'neutral','manual'),row(4,'watched'),row(5,'like')]);
 assert.equal(result.recommended.precision,.5);assert.equal(result.recommended.neutral,1);assert.equal(result.recommended.total,3);
 assert.equal(result.all.precision,2/3);assert.equal(result.all.watched,1);
});
test('duplicate films use the most recent opinion and invalid IDs are ignored',()=>{
 const result=ratingSummary([{tmdb_id:1,impression:'like',updated_at:'2026-01-02'},{tmdb_id:1,impression:'dislike',updated_at:'2026-01-01'},{tmdb_id:'1',impression:'dislike'}]);
 assert.equal(result.all.total,1);assert.equal(result.all.precision,1);
});
test('no decisive recommendations yields an unavailable percentage, never a fabricated zero',()=>{
 assert.equal(ratingSummary([]).recommended.precision,null);
 assert.equal(ratingSummary([{tmdb_id:1,impression:'neutral',metadata:{recommendationMode:'manual'}}]).recommended.precision,null);
});
test('recent failed recommendations are visible even when lifetime precision is higher',()=>{
 const rows=Array.from({length:60},(_,i)=>({tmdb_id:i+1,updated_at:new Date(Date.UTC(2026,0,i+1)).toISOString(),impression:i<30?'like':'dislike',metadata:{recommendationMode:'manual'}}));
 const result=ratingSummary(rows);
 assert.equal(result.recommended.precision,.5);assert.equal(result.latest.total,30);assert.equal(result.latest.precision,0);
 assert.equal(result.latest.dislike,30);
});
test('admission calibration requires dated chronological evidence and enough positive validation films',()=>{
 assert.equal(selectionFloor([]),null);
 assert.equal(selectionFloor(Array.from({length:120},(_,i)=>({tmdb_id:i+1,impression:'dislike',metadata:{}}))),null);
 assert.equal(evaluateSelection([]).status,'insufficient');
});
test('validation labels cannot change the learned threshold or training count',()=>{
 const rows=Array.from({length:400},(_,i)=>({tmdb_id:i+1,updated_at:new Date(Date.UTC(2025,0,1+i)).toISOString(),impression:i%5?'dislike':'like',metadata:{productionBudget:15000000,year:2021,genreIds:[27],keywords:[i%5?'haunted house':'body horror'],originalLanguage:'en'}}));
 const before=evaluateSelection(rows);
 const changed=rows.map((r,i)=>i<320?r:{...r,impression:r.impression==='like'?'dislike':'like'});
 const after=evaluateSelection(changed);
 assert.equal(before.training,320);assert.equal(after.training,320);assert.equal(before.floor,after.floor);
 assert.equal(before.after.accepted,30);assert.equal(before.metric,'top_30');
});
