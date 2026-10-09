import {serverConfig} from './server-config.js';
export class ServerStore {
 constructor(config=serverConfig,request=(...args)=>fetch(...args)){this.config=config;this.request=request;this.session=null;this.configured=Boolean(config.url&&config.publishableKey);}
 async api(path,{method='GET',body,auth=true,headers={}}={}){
  if(!this.configured)throw new Error('Сервер пока не подключён.');
  if(auth){if(!this.session)throw new Error('Войдите, чтобы сохранить оценку на сервере.');if(this.session.expires_at*1000<Date.now()+60000)await this.refresh();}
  const response=await this.request(this.config.url.replace(/\/$/,'')+path,{method,headers:{apikey:this.config.publishableKey,...(auth?{Authorization:'Bearer '+this.session.access_token}:{}),'Content-Type':'application/json',...headers},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});
  if(!response.ok){let code;try{code=(await response.json()).code;}catch{}throw new Error(code==='PGRST205'?'Таблицы сервера ещё не созданы: выполните schema.sql в Supabase.':response.status===401?'Проверьте подключение и войдите снова.':response.status===429?'Слишком много запросов. Попробуйте позже.':'Сервер не подтвердил операцию. Попробуйте ещё раз.');}
  const text=await response.text();return text?JSON.parse(text):null;
 }
 remember(session){this.session={...session,expires_at:session.expires_at||Math.floor(Date.now()/1000)+session.expires_in};sessionStorage.setItem('nightshift.session',JSON.stringify(this.session));}
 async restore(){try{const session=JSON.parse(sessionStorage.getItem('nightshift.session')||'null');if(!session?.refresh_token)return false;this.session=session;await this.refresh();await this.api('/auth/v1/user');return true;}catch{this.session=null;sessionStorage.removeItem('nightshift.session');return false;}}
 async refresh(){const value=await this.api('/auth/v1/token?grant_type=refresh_token',{method:'POST',auth:false,body:{refresh_token:this.session.refresh_token}});this.remember(value);}
 async sendCode(email){await this.api('/auth/v1/otp',{method:'POST',auth:false,body:{email,create_user:true}});}
 async verify(email,token){const session=await this.api('/auth/v1/verify',{method:'POST',auth:false,body:{email,token,type:'email'}});this.remember(session);await this.api('/rest/v1/profiles?on_conflict=user_id',{method:'POST',body:{user_id:this.session.user.id},headers:{Prefer:'resolution=ignore-duplicates'}});}
 async load(){return await Promise.all([this.api('/rest/v1/ratings?select=*'),this.api('/rest/v1/collection?select=*&order=created_at.desc')]);}
 async saveRating(f,r){if(!this.session)throw new Error('Войдите, чтобы сохранить оценку на сервере.');return this.api('/rest/v1/ratings?on_conflict=user_id,tmdb_id',{method:'POST',body:{user_id:this.session.user.id,tmdb_id:f.tmdbId,cinematography:r.cinematography??null,plot:r.plot??null,impression:r.impression,metadata:f,updated_at:r.ratedAt||new Date().toISOString()},headers:{Prefer:'resolution=merge-duplicates,return=representation'}});}
 async deleteRating(f){await this.api('/rest/v1/ratings?tmdb_id=eq.'+f.tmdbId,{method:'DELETE'});}
 async clearRatings(){await this.api('/rest/v1/ratings?user_id=eq.'+this.session.user.id,{method:'DELETE'});}
 async saveCollection(f,saved){if(!this.session)throw new Error('Войдите, чтобы сохранить коллекцию.');await this.api('/rest/v1/collection?on_conflict=user_id,tmdb_id',{method:'POST',body:{user_id:this.session.user.id,tmdb_id:f.tmdbId,metadata:f,saved},headers:{Prefer:'resolution=merge-duplicates'}});}
 async logout(){try{if(this.session)await this.api('/auth/v1/logout',{method:'POST'});}finally{this.session=null;sessionStorage.removeItem('nightshift.session');}}
}
