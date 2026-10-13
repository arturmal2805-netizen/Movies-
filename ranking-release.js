// Update ranking in an open tab without reloading the feed or interrupting input.
const validVersion=value=>typeof value==='string'&&/^quality[1-9]\d*[a-z]?$/.test(value);
const order=value=>[Number(value.match(/\d+/)[0]),value.match(/[a-z]$/)?.[0]||''];
export class RankingReleaseMonitor {
 constructor({version,fetchManifest,loadRanking,onUpdate,canApply=()=>true}){
  this.version=version;this.fetchManifest=fetchManifest;this.loadRanking=loadRanking;this.onUpdate=onUpdate;this.canApply=canApply;this.checking=false;
 }
 async check(){
  if(this.checking)return false;
  this.checking=true;
  try{
   const manifest=await this.fetchManifest();
   if(!validVersion(manifest?.version)||!validVersion(this.version)||typeof manifest.selection!=='string'||!/^audience-(first|priority)\d+$/.test(manifest.selection))return false;
   const [major,suffix]=order(manifest.version),[current,revision]=order(this.version);
   if(major<current||major===current&&suffix<=revision||!this.canApply())return false;
   const ranking=await this.loadRanking(manifest.version);
   if(!['selectionScore','selectionSecondaryScore','compareSelection','buildSelectionProfile'].every(k=>typeof ranking?.[k]==='function')||ranking.selectionVersion!==manifest.selection||!this.canApply())return false;
   await this.onUpdate(ranking,manifest.version);
   this.version=manifest.version;return true;
  }catch{return false;}
  finally{this.checking=false;}
 }
}
