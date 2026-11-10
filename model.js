export const STAGES=['Очікує дату готовності','Країна відправника','Забір','Перевезення','Склад у Польщі','Митниця','Розмитнення','Київ'];
export const TRANSPORT_TYPES={express:'Експрес перевезення',freight:'Фрахт'};
export const FREIGHT_STAGES=[...STAGES.slice(0,3),'ПД · Попереднє декларування',...STAGES.slice(3)];
export function stagesFor(type='express'){return type==='freight'?FREIGHT_STAGES:STAGES;}
export const FIELDS=['name','country','carrier','manufacturer','origin','destination','eta','readyDate','tracking','weight','contact','notes','logo'];
export const STORAGE_KEY='artur-logistics.orders.v1';
const limits={name:120,country:80,carrier:120,manufacturer:160,origin:240,destination:240,eta:10,readyDate:10,tracking:120,weight:30,contact:160,notes:3000,logo:4};
export function validateOrder(raw){
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('Невірний формат замовлення.');
 const transportType=raw.transportType??'express';
 if(!Object.hasOwn(TRANSPORT_TYPES,transportType))throw Error('Невідомий тип перевезення.');
 const stages=stagesFor(transportType);
 if(raw.stageSchema!==undefined&&raw.stageSchema!==2)throw Error('Невідома версія етапів.');
 if(raw.stageSchema===undefined){
  if(!Number.isInteger(raw.stage)||raw.stage<0||raw.stage>=stages.length-1)throw Error('Невідомий етап доставки.');
  const history=Array.isArray(raw.history)?raw.history:[];
  if(history.some(h=>!h||!Number.isInteger(h.stage)||h.stage<0||h.stage>=stages.length-1))throw Error('Невірна історія етапів.');
  raw={...raw,stage:raw.stage+1,history:history.map(h=>({...h,stage:h.stage+1}))};
 }
 const result={transportType,stageSchema:2};
 for(const key of FIELDS){if(raw[key]!==undefined&&typeof raw[key]!=='string')throw Error('Невірне поле: '+key);result[key]=(raw[key]||'').trim();if(result[key].length>limits[key])throw Error('Завелике поле: '+key);}
 if(!['','apr','none'].includes(result.logo))throw Error('Невідомий логотип компанії.');
 if(!result.name||!result.country)throw Error('Вкажіть назву папки та країну відправника.');
 if(!Number.isInteger(raw.stage)||raw.stage<0||raw.stage>=stages.length)throw Error('Невідомий етап доставки.');
 if(result.weight&&(!Number.isFinite(Number(result.weight))||Number(result.weight)<0||Number(result.weight)>10000000))throw Error('Перевірте вагу вантажу.');
 for(const field of ['eta','readyDate'])if(result[field]&&(!/^\d{4}-\d{2}-\d{2}$/.test(result[field])||!Number.isFinite(Date.parse(result[field]))||new Date(result[field]).toISOString().slice(0,10)!==result[field]))throw Error('Перевірте дату доставки.');
 if(typeof raw.id!=='string'||!/^[a-zA-Z0-9-]{1,80}$/.test(raw.id))throw Error('Невірний ідентифікатор папки.');
 result.id=raw.id;result.stage=raw.stage;
 if(raw.attention!==undefined&&typeof raw.attention!=='boolean')throw Error('Невірна позначка уваги.');
 result.attention=raw.attention===true;
 for(const key of ['createdAt','updatedAt']){if(typeof raw[key]!=='string'||!Number.isFinite(Date.parse(raw[key])))throw Error('Невірна дата замовлення.');result[key]=raw[key];}
 result.history=(Array.isArray(raw.history)?raw.history:[]).slice(-100).map(h=>{if(!h||!Number.isInteger(h.stage)||h.stage<0||h.stage>=stages.length||typeof h.at!=='string'||!Number.isFinite(Date.parse(h.at)))throw Error('Невірна історія етапів.');return {stage:h.stage,at:h.at};});
 return result;
}
export function parseBackup(text){
 const backup=JSON.parse(text);
 if(!backup||backup.version!==1||!Array.isArray(backup.orders)||backup.orders.length>10000)throw Error('Оберіть резервну копію ARTUR логістик (до 10 000 папок).');
 const orders=backup.orders.map(validateOrder);
 if(new Set(orders.map(o=>o.id)).size!==orders.length)throw Error('У копії повторюються ідентифікатори папок.');
 return orders;
}
export function moveOrder(order,stage,at=new Date().toISOString()){
 if(!Number.isInteger(stage)||stage<0||stage>=stagesFor(order.transportType).length)throw Error('Невідомий етап.');
 return order.stage===stage?order:{...order,stage,attention:false,updatedAt:at,history:[...order.history,{stage,at}].slice(-100)};
}
export function mergeOrders(current,incoming){
 const result=new Map(current.map(o=>[o.id,o]));
 for(const order of incoming){const previous=result.get(order.id);if(!previous||Date.parse(order.updatedAt)>Date.parse(previous.updatedAt))result.set(order.id,order);}
 return [...result.values()];
}

export function latestReadyDate(orders,type){
 return orders.filter(o=>o.transportType===type&&o.stage===0&&o.readyDate).map(o=>o.readyDate).sort().at(-1)||'';
}

export function logoFor(order){
 if(order.logo==='none')return null;
 if(order.logo==='apr'||/\bapr\b|anton\s*paar|антон\s*паар/i.test((order.manufacturer||'')+' '+(order.name||'')))return {src:'apr.avif',alt:'APR · Anton Paar'};
 return null;
}
