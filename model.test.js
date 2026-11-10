import test from 'node:test';
import assert from 'node:assert/strict';
import {validateOrder,parseBackup,moveOrder,mergeOrders,STAGES,FREIGHT_STAGES,stagesFor} from './model.js';
const order=()=>validateOrder({id:'order-1',name:'Обладнання',country:'Польща',stage:0,createdAt:'2026-11-09T10:00:00Z',updatedAt:'2026-11-09T10:00:00Z',history:[{stage:0,at:'2026-11-09T10:00:00Z'}]});
test('create and move a folder through all seven stages without losing its data',()=>{let o=order();for(let stage=1;stage<STAGES.length;stage++)o=moveOrder(o,stage,'2026-11-09T12:00:00Z');assert.equal(o.stage,6);assert.equal(o.history.length,7);assert.equal(o.country,'Польща');assert.equal(o.name,'Обладнання');assert.equal(moveOrder(o,6),o);});
test('export/import preserves folder details and full route history',()=>{const o=moveOrder({...order(),notes:'Документи готові',carrier:'Перевізник'},3);assert.deepEqual(parseBackup(JSON.stringify({version:1,orders:[o]})),[o]);});
test('invalid backups cannot overwrite state',()=>{for(const value of [{version:1,orders:[{...order(),stage:7}]},{version:1,orders:[order(),order()]},{version:1,orders:[{...order(),name:''}]},{version:1,orders:[{...order(),eta:'2026-02-30'}]},{version:1,orders:[{...order(),weight:'-1'}]},{version:1,orders:[{...order(),history:[{stage:99,at:'bad'}]}]}])assert.throws(()=>parseBackup(JSON.stringify(value)));});
test('import merges unique orders and retains the newest edited version',()=>{const older=order(),newer=moveOrder(older,4,'2026-11-09T12:00:00Z'),other={...older,id:'order-2'};assert.deepEqual(mergeOrders([newer],[older,other]),[newer,other]);assert.deepEqual(mergeOrders([older],[newer]),[newer]);});
test('stored data is allowlisted and unsafe shape rejected',()=>{assert.equal(validateOrder({...order(),unknown:'discard'}).unknown,undefined);assert.throws(()=>validateOrder({...order(),notes:{html:'x'}}));assert.throws(()=>moveOrder(order(),-1));});

test('legacy backups default to express without shifting any stage or history',()=>{
 const legacy={...order(),stage:4,history:[{stage:2,at:'2026-11-09T10:00:00Z'}]};delete legacy.transportType;
 const restored=parseBackup(JSON.stringify({version:1,orders:[legacy]}))[0];
 assert.equal(restored.transportType,'express');assert.equal(STAGES[restored.stage],'Митниця');assert.equal(STAGES[restored.history[0].stage],'Перевезення');
});
test('freight adds PD strictly between pickup and transport, then completes to Kyiv',()=>{
 assert.deepEqual(FREIGHT_STAGES,[...STAGES.slice(0,2),'ПД · Попереднє декларування',...STAGES.slice(2)]);
 let freight=validateOrder({...order(),transportType:'freight'});
 for(let stage=1;stage<8;stage++)freight=moveOrder(freight,stage);
 assert.equal(freight.stage,7);assert.equal(stagesFor(freight.transportType)[freight.stage],'Київ');
 assert.equal(freight.history.length,8);
 assert.deepEqual(parseBackup(JSON.stringify({version:1,orders:[freight]})),[freight]);
 assert.throws(()=>moveOrder(order(),7));
});
test('both transport types remain distinct across merging and backup',()=>{
 const express=order(),freight=validateOrder({...order(),id:'freight-1',transportType:'freight',stage:2});
 const restored=parseBackup(JSON.stringify({version:1,orders:mergeOrders([express],[freight])}));
 assert.equal(restored[0].transportType,'express');assert.equal(restored[1].transportType,'freight');assert.equal(stagesFor(restored[1].transportType)[2],'ПД · Попереднє декларування');
 assert.throws(()=>validateOrder({...order(),transportType:'unknown'}));
});
