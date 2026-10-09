const terminal=new Set(['completed','failed']);
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export class ManualRecommendations {
 constructor(server,{onState=()=>{},onComplete=async()=>{},schedule=(fn,ms)=>setTimeout(fn,ms),cancel=id=>clearTimeout(id)}={}){
  this.server=server;this.onState=onState;this.onComplete=onComplete;this.schedule=schedule;this.cancel=cancel;this.job=null;this.starting=false;this.timer=null;this.generation=0;
 }
 key(){return 'nightshift.manual-job.'+this.server.session?.user?.id;}
 remember(job){if(job)localStorage.setItem(this.key(),JSON.stringify({id:job.id}));else localStorage.removeItem(this.key());}
 valid(job){return job&&uuid.test(job.id)&&['queued','running','completed','failed'].includes(job.status);}
 async start(){
  if(!this.server.session)throw new Error('Войдите, чтобы запустить персональный подбор.');
  if(this.starting||this.job&&!terminal.has(this.job.status))return this.job;
  const generation=this.generation;this.starting=true;this.onState({status:'starting'});
  try{
   const job=await this.server.startRecommendations();if(!this.valid(job))throw new Error('Сервер не подтвердил запуск подбора.');
   if(generation!==this.generation)return null;
   this.job=job;this.remember(job);this.onState(job);this.queue(generation);return job;
  }catch(error){if(generation===this.generation)this.onState({status:'error',message:error.message});throw error;}
  finally{if(generation===this.generation)this.starting=false;}
 }
 queue(generation=this.generation){this.cancel(this.timer);this.timer=this.schedule(()=>this.poll(generation),4000);}
 async poll(generation=this.generation){
  if(!this.job||generation!==this.generation||!this.server.session)return;
  try{
   const job=await this.server.recommendationStatus(this.job.id);if(!this.valid(job))throw new Error('Статус подбора временно недоступен.');
   if(generation!==this.generation)return;
   this.job=job;
   if(terminal.has(job.status)){
    this.remember(null);
    if(job.status==='completed'){
     try{await this.onComplete(job);}catch{job.syncPending=true;}
    }
    if(generation===this.generation)this.onState(job);
    return;
   }
   this.onState(job);this.queue(generation);
  }catch(error){
   if(generation===this.generation){this.onState({...this.job,connectionLost:true});this.queue(generation);}
  }
 }
 async resume(){
  this.stop();const generation=this.generation;if(!this.server.session)return;
  try{
   let stored;try{stored=JSON.parse(localStorage.getItem(this.key())||'null');}catch{}
   let job=stored&&uuid.test(stored.id)?{id:stored.id,status:'queued'}:await this.server.activeRecommendation();
   if(generation!==this.generation||!this.valid(job))return;
   this.job=job;this.onState(job);await this.poll(generation);
  }catch{ /* Missing optional manual setup must not prevent normal account synchronization. */ }
 }
 stop(){this.generation++;this.cancel(this.timer);this.timer=null;this.job=null;this.starting=false;}
}
