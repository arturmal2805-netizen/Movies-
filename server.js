import {serverConfig} from './server-config.js';
export class ServerStore {
 constructor(config=serverConfig,request=(...args)=>fetch(...args)){this.config=config;this.request=request;this.session=null;this.refreshPromise=null;this.configured=Boolean(config.url&&config.publishableKey);}
 async api(path,{method='GET',body,auth=true,headers={}}={}){
  if(!this.configured)throw new Error('Сервер пока не подключён.');
  if(auth){if(!this.session)throw new Error('Войдите, чтобы сохранить оценку на сервере.');if(this.session.expires_at*1000<Date.now()+60000)await this.refresh();}
  const response=await this.request(this.config.url.replace(/\/$/,'')+path,{method,headers:{apikey:this.config.publishableKey,...(auth?{Authorization:'Bearer '+this.session.access_token}:{}),'Content-Type':'application/json',...headers},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});
  if(!response.ok){let code,message;try{const value=await response.json();code=value.code;message=value.message;}catch{}const manualSetup=path.startsWith('/rest/v1/rpc/')&&(code==='PGRST202'||message==='manual_not_configured');const error=new Error(manualSetup?'Ручной подбор ещё не подключён. Нужна настройка запуска GitHub.':path.startsWith('/auth/v1/otp')&&response.status>=500?'Не удалось отправить письмо. Проверьте SMTP в Supabase: логин, пароль приложения и адрес отправителя.':code==='otp_expired'?'Код неверный или истёк. Запросите новый код.':code==='email_address_not_authorized'?'Почтовый сервис пока не разрешает отправку на этот адрес.':code==='PGRST205'?'Таблицы сервера ещё не созданы: выполните schema.sql в Supabase.':response.status===401?'Проверьте подключение и войдите снова.':response.status===429?'Слишком много запросов. Попробуйте позже.':'Сервер не подтвердил операцию. Попробуйте ещё раз.');error.status=response.status;error.code=code;throw error;}
  const text=await response.text();return text?JSON.parse(text):null;
 }
 readSession(){try{return JSON.parse(localStorage.getItem('nightshift.session')||sessionStorage.getItem('nightshift.session')||'null');}catch{return null;}}
 clearSession(){this.session=null;localStorage.removeItem('nightshift.session');sessionStorage.removeItem('nightshift.session');}
 remember(session){this.session={...session,expires_at:session.expires_at||Math.floor(Date.now()/1000)+(session.expires_in||3600)};localStorage.setItem('nightshift.session',JSON.stringify(this.session));sessionStorage.removeItem('nightshift.session');}
 async restore(){
  const session=this.readSession();if(!session?.refresh_token)return false;this.session=session;
  try{
   if(session.expires_at*1000<Date.now()+60000)await this.refresh();
   const user=await this.api('/auth/v1/user');if(!user?.id){this.clearSession();return false;}
   this.remember({...this.session,user});return true;
  }catch(error){if([400,401,403].includes(error.status)){this.clearSession();return false;}throw error;}
 }
 async refresh(){
  if(this.refreshPromise)return this.refreshPromise;
  const renew=async()=>{
   // Another tab may already have rotated the refresh token while we waited.
   const stored=this.readSession();if(stored?.refresh_token&&stored.refresh_token!==this.session?.refresh_token)this.session=stored;
   if(this.session?.expires_at*1000>=Date.now()+60000)return;
   try{const value=await this.api('/auth/v1/token?grant_type=refresh_token',{method:'POST',auth:false,body:{refresh_token:this.session.refresh_token}});this.remember(value);}
   catch(error){if([400,401,403].includes(error.status))this.clearSession();throw error;}
  };
  const locks=globalThis.navigator?.locks;
  this.refreshPromise=locks?locks.request('nightshift-auth-refresh',renew):renew();
  try{await this.refreshPromise;}finally{this.refreshPromise=null;}
 }
 async sendCode(email,redirectTo){await this.api('/auth/v1/otp'+(redirectTo?'?redirect_to='+encodeURIComponent(redirectTo):''),{method:'POST',auth:false,body:{email,create_user:true}});}
 async verify(email,token){const session=await this.api('/auth/v1/verify',{method:'POST',auth:false,body:{email,token,type:'email'}});this.remember(session);await this.api('/rest/v1/profiles?on_conflict=user_id',{method:'POST',body:{user_id:this.session.user.id},headers:{Prefer:'resolution=ignore-duplicates'}});}
 async ensureProfile(){await this.api('/rest/v1/profiles?on_conflict=user_id',{method:'POST',body:{user_id:this.session.user.id},headers:{Prefer:'resolution=ignore-duplicates'}});}
 async acceptLink(fragment){
  const params=new URLSearchParams(fragment.replace(/^#/,''));
  if(params.has('error'))throw new Error('Ссылка входа истекла. Запросите новое письмо.');
  const access=params.get('access_token'),refresh=params.get('refresh_token');
  if(!access||!refresh)return false;
  try{
   const expires=Number(params.get('expires_in'))||3600;
   this.session={access_token:access,refresh_token:refresh,expires_at:Math.floor(Date.now()/1000)+Math.min(Math.max(expires,60),86400)};
   const user=await this.api('/auth/v1/user');
   if(!user?.id)throw new Error('Ссылка входа недействительна.');
   this.remember({...this.session,user});await this.ensureProfile();return true;
  }catch(error){this.clearSession();throw error;}
 }
 async load(){return await Promise.all([this.api('/rest/v1/ratings?select=*'),this.api('/rest/v1/collection?select=*&order=created_at.desc')]);}
 async saveRating(f,r){if(!this.session)throw new Error('Войдите, чтобы сохранить оценку на сервере.');return this.api('/rest/v1/ratings?on_conflict=user_id,tmdb_id',{method:'POST',body:{user_id:this.session.user.id,tmdb_id:f.tmdbId,cinematography:r.cinematography??null,plot:r.plot??null,impression:r.impression,metadata:f,updated_at:r.ratedAt||new Date().toISOString()},headers:{Prefer:'resolution=merge-duplicates,return=representation'}});}
 async deleteRating(f){await this.api('/rest/v1/ratings?tmdb_id=eq.'+f.tmdbId,{method:'DELETE'});}
 async clearRatings(){await this.api('/rest/v1/ratings?user_id=eq.'+this.session.user.id,{method:'DELETE'});}
 async saveCollection(f,saved){if(!this.session)throw new Error('Войдите, чтобы сохранить коллекцию.');await this.api('/rest/v1/collection?on_conflict=user_id,tmdb_id',{method:'POST',body:{user_id:this.session.user.id,tmdb_id:f.tmdbId,metadata:f,saved},headers:{Prefer:'resolution=merge-duplicates'}});}
 async startRecommendations(){return this.api('/rest/v1/rpc/start_manual_recommendation',{method:'POST',body:{}});}
 async recommendationStatus(id){return this.api('/rest/v1/rpc/manual_recommendation_status',{method:'POST',body:{job_id:id}});}
 async activeRecommendation(){const rows=await this.api('/rest/v1/recommendation_jobs?select=id,status&status=in.(queued,running)&order=created_at.desc&limit=1');return rows?.[0]||null;}
 async logout(){try{if(this.session)await this.api('/auth/v1/logout',{method:'POST'});}finally{this.clearSession();}}
}
