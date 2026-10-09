const memory=new Map();globalThis.localStorage={getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
import test from 'node:test';import assert from 'node:assert/strict';import {ServerStore} from './server.js';
test('server ratings require authentication and do not silently save locally',async()=>{const s=new ServerStore({url:'https://example.com',publishableKey:'public'},()=>{throw Error('unexpected request')});await assert.rejects(s.saveRating({tmdbId:1},{}),/Войдите/);});
test('rating is sent with user ID, TMDB ID and both scales',async()=>{let sent;const s=new ServerStore({url:'https://example.com',publishableKey:'public'},async(url,options)=>{sent={url,...options};return new Response('[]',{status:200});});s.session={user:{id:'user-1'},access_token:'test-token',expires_at:Date.now()/1000+3600};await s.saveRating({tmdbId:157336},{cinematography:8,plot:9,impression:'like'});const body=JSON.parse(sent.body);assert.equal(body.user_id,'user-1');assert.equal(body.plot,9);assert.equal(body.cinematography,8);assert.equal(body.tmdb_id,157336);assert.equal(sent.headers.Authorization,'Bearer test-token');});
test('failed writes reject instead of reporting success',async()=>{const s=new ServerStore({url:'https://example.com',publishableKey:'public'},async()=>new Response('',{status:503}));s.session={user:{id:'user'},access_token:'token',expires_at:Date.now()/1000+3600};await assert.rejects(s.saveRating({tmdbId:1},{impression:'like'}),/не подтвердил/);});
test('email link authenticates against Supabase before accepting user identity',async()=>{const memory=new Map();globalThis.sessionStorage={setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};const calls=[];const s=new ServerStore({url:'https://example.com',publishableKey:'public'},async(url)=>{calls.push(url);return new Response(JSON.stringify(url.includes('/auth/v1/user')?{id:'verified-user'}:[]));});assert.equal(await s.acceptLink('#access_token=fake-access&refresh_token=fake-refresh&expires_in=3600'),true);assert.equal(s.session.user.id,'verified-user');assert.ok(calls[0].endsWith('/auth/v1/user'));assert.ok(localStorage.getItem('nightshift.session'));assert.equal(memory.has('nightshift.session'),false);});
test('invalid link cannot create an authenticated session',async()=>{globalThis.sessionStorage={setItem:()=>{},removeItem:()=>{}};const s=new ServerStore({url:'https://example.com',publishableKey:'public'},async()=>new Response('',{status:401}));await assert.rejects(s.acceptLink('#access_token=fake&refresh_token=fake'));assert.equal(s.session,null);});
function resetStorage(){memory.clear();const temp=new Map();globalThis.sessionStorage={getItem:k=>temp.get(k)||null,setItem:(k,v)=>temp.set(k,v),removeItem:k=>temp.delete(k)};return temp;}
function session(expires=3600){return {access_token:'test-access',refresh_token:'test-refresh',expires_at:Date.now()/1000+expires,user:{id:'test-user'}};}
test('email OTP is requested and verified, then survives a fresh store',async()=>{
 resetStorage();const calls=[];const request=async(url,options)=>{calls.push({url,body:options.body&&JSON.parse(options.body)});return new Response(JSON.stringify(url.endsWith('/verify')?session():url.endsWith('/user')?{id:'test-user'}:[]));};
 const s=new ServerStore({url:'https://example.com',publishableKey:'public'},request);
 await s.sendCode('test@example.com');await s.verify('test@example.com','123456');
 assert.deepEqual(calls[0].body,{email:'test@example.com',create_user:true});assert.equal(calls[1].body.token,'123456');assert.equal(calls[1].body.type,'email');
 const reopened=new ServerStore(s.config,request);assert.equal(await reopened.restore(),true);assert.equal(reopened.session.user.id,'test-user');assert.equal(calls.filter(c=>c.url.includes('grant_type')).length,0);
});
test('expired session refresh is shared by concurrent authenticated requests',async()=>{
 resetStorage();let refreshes=0;const s=new ServerStore({url:'https://example.com',publishableKey:'public'},async(url)=>{
 if(url.includes('grant_type')){refreshes++;await new Promise(resolve=>setTimeout(resolve,5));return new Response(JSON.stringify({...session(),refresh_token:'rotated'}));}return new Response('[]');
 });s.remember(session(-1));await Promise.all([s.api('/rest/v1/ratings'),s.api('/rest/v1/collection')]);
 assert.equal(refreshes,1);assert.equal(JSON.parse(localStorage.getItem('nightshift.session')).refresh_token,'rotated');
});
test('temporary server failure preserves login; revoked refresh clears it',async()=>{
 resetStorage();const s=new ServerStore({url:'https://example.com',publishableKey:'public'},async()=>new Response('',{status:503}));s.remember(session(-1));await assert.rejects(s.restore());assert.ok(localStorage.getItem('nightshift.session'));
 s.request=async()=>new Response('',{status:401});assert.equal(await s.restore(),false);assert.equal(localStorage.getItem('nightshift.session'),null);
});
test('session-only legacy login migrates and explicit logout clears both stores',async()=>{
 const temp=resetStorage();temp.set('nightshift.session',JSON.stringify(session()));const s=new ServerStore({url:'https://example.com',publishableKey:'public'},async url=>new Response(JSON.stringify(url.endsWith('/user')?{id:'test-user'}:[])));
 assert.equal(await s.restore(),true);assert.ok(localStorage.getItem('nightshift.session'));assert.equal(temp.size,0);await s.logout();assert.equal(localStorage.getItem('nightshift.session'),null);assert.equal(s.session,null);
});
test('SMTP failure is reported as delivery failure without creating a session',async()=>{
 resetStorage();const s=new ServerStore({url:'https://example.com',publishableKey:'public'},async()=>new Response(JSON.stringify({code:'unexpected_failure'}),{status:500}));
 await assert.rejects(s.sendCode('test@example.com'),e=>e.status===500&&/SMTP/.test(e.message));assert.equal(s.session,null);assert.equal(localStorage.getItem('nightshift.session'),null);
});
test('manual recommendation dispatch uses account authentication without trusting a client user ID',async()=>{
 let sent;const s=new ServerStore({url:'https://example.com',publishableKey:'public'},async(url,options)=>{sent={url,...options};return new Response(JSON.stringify({id:'00000000-0000-4000-8000-000000000001',status:'queued'}));});s.session=session();await s.startRecommendations();assert.ok(sent.url.endsWith('/rpc/start_manual_recommendation'));assert.equal(sent.headers.Authorization,'Bearer test-access');assert.deepEqual(JSON.parse(sent.body),{});
});
test('uninstalled manual RPC gives a concrete setup error',async()=>{
 const s=new ServerStore({url:'https://example.com',publishableKey:'public'},async()=>new Response(JSON.stringify({code:'PGRST202',message:'function missing'}),{status:404}));s.session=session();await assert.rejects(s.startRecommendations(),/Ручной подбор ещё не подключён/);
});

test('all ratings are paginated beyond 525 and 1000 rows without truncation',async()=>{
 const rows=Array.from({length:1250},(_,tmdb_id)=>({tmdb_id}));const store=new ServerStore();let calls=0;
 store.api=async path=>{calls++;const params=new URL('http://test'+path).searchParams;assert.equal(params.get('order'),'tmdb_id');const offset=Number(params.get('offset'));return rows.slice(offset,offset+Number(params.get('limit')));};
 assert.equal((await store.readAll('ratings')).length,1250);assert.equal(calls,3);
});
