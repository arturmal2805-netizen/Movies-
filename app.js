import {STAGES,TRANSPORT_TYPES,stagesFor,FIELDS,STORAGE_KEY,validateOrder,parseBackup,moveOrder,mergeOrders} from './model.js';
const $=s=>document.querySelector(s),form=$('#orderForm'),dialog=$('#orderDialog'),detail=$('#detailDialog');
let orders=[],editing=null,selected=null,dragged=null,toastTimer;
const stageOptions=(type='express')=>stagesFor(type).map((s,i)=>new Option(s,String(i)));
form.elements.stage.replaceChildren(...stageOptions());
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,5000);}
let storageBroken=false;
try{const saved=localStorage.getItem(STORAGE_KEY);if(saved)orders=parseBackup(saved);}catch{storageBroken=true;toast('Не вдалося прочитати дані. Експортуйте резервну копію або перевірте доступ до сховища браузера.');}
function persist(next){
 if(storageBroken){toast('Сховище недоступне або пошкоджене. Щоб не втратити дані, спершу перевірте його в налаштуваннях браузера.');return false;}
 try{localStorage.setItem(STORAGE_KEY,JSON.stringify({version:1,orders:next}));orders=next;$('#saveState').textContent='усі зміни збережені';render();return true;}
 catch{toast('Не вдалося зберегти зміни. Сховище браузера заповнене або недоступне.');return false;}
}
function element(tag,className,text){const el=document.createElement(tag);if(className)el.className=className;if(text!==undefined)el.textContent=text;return el;}
function localDate(date){return date?new Intl.DateTimeFormat('uk-UA',{day:'2-digit',month:'short',year:'numeric',timeZone:'Europe/Kyiv'}).format(new Date(date)): 'Без дати';}
function today(){return new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Kyiv',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());}
function reference(order){return 'AL · '+order.id.slice(0,6).toUpperCase();}
function openForm(order=null,stage=0,type='express'){
 editing=order?.id||null;form.reset();$('#dialogTitle').textContent=order?'Редагувати замовлення':'Нове замовлення';
 for(const field of FIELDS)if(form.elements[field])form.elements[field].value=order?.[field]||'';
 form.elements.transportType.value=order?.transportType||type;
 form.elements.transportType.disabled=Boolean(order);
 form.elements.stage.replaceChildren(...stageOptions(form.elements.transportType.value));
 form.elements.stage.value=String(order?.stage??stage);
 $('#stepOne').hidden=false;$('#stepTwo').hidden=true;form.elements.country.required=false;
 dialog.showModal();form.elements.name.focus();
}
function nextStep(){if(!form.elements.name.reportValidity())return;$('#stepOne').hidden=true;$('#stepTwo').hidden=false;form.elements.country.required=true;form.elements.country.focus();}
form.elements.transportType.onchange=()=>{
 const previousLabel=form.elements.stage.selectedOptions[0]?.textContent;
 form.elements.stage.replaceChildren(...stageOptions(form.elements.transportType.value));
 const index=stagesFor(form.elements.transportType.value).indexOf(previousLabel);
 form.elements.stage.value=String(Math.max(0,index));
};
$('#next').onclick=nextStep;
$('#back').onclick=()=>{$('#stepOne').hidden=false;$('#stepTwo').hidden=true;form.elements.country.required=false;form.elements.name.focus();};
$('#addExpress').onclick=()=>openForm(null,0,'express');$('#addFreight').onclick=()=>openForm(null,0,'freight');
$('#add').onclick=()=>openForm();$('#emptyAdd').onclick=()=>openForm();
$('#close').onclick=()=>dialog.close();document.querySelectorAll('.cancel').forEach(b=>b.onclick=()=>dialog.close());
form.addEventListener('submit',event=>{
 event.preventDefault();if(!$('#stepOne').hidden){nextStep();return;}
 const now=new Date().toISOString(),previous=orders.find(o=>o.id===editing),data=Object.fromEntries(new FormData(form));
 try{
  let order=validateOrder({...previous,...data,transportType:previous?.transportType||data.transportType,id:previous?.id||crypto.randomUUID(),stage:previous?.stage??Number(data.stage),createdAt:previous?.createdAt||now,updatedAt:now,history:previous?.history||[{stage:Number(data.stage),at:now}]});
  order=moveOrder(order,Number(data.stage),now);
  if(persist(previous?orders.map(o=>o.id===order.id?order:o):[order,...orders])){dialog.close();toast(previous?'Зміни збережено':'Папку замовлення створено');}
 }catch(error){toast(error.message);}
});
function changeStage(id,stage){
 const order=orders.find(o=>o.id===id);if(!order||order.stage===stage)return;
 try{if(persist(orders.map(o=>o.id===id?moveOrder(o,stage):o))){toast('Етап: '+stagesFor(order.transportType)[stage]);if(detail.open)showDetail(id,false);}}catch(error){toast(error.message);}
}
function makeCard(order){
 const card=element('article','card');card.draggable=true;card.dataset.id=order.id;
 const open=element('button','card-open');open.type='button';open.setAttribute('aria-label','Відкрити папку '+order.name);
 const ref=element('div','card-reference');ref.append(element('span','folder-icon','▱'),element('span','',reference(order)));
 open.append(ref,element('h3','',order.name),element('span','country-tag',order.country));
 open.append(element('div','card-route',(order.manufacturer||'Виробник')+' → Київ'));
 const bottom=element('div','card-bottom');
 const late=order.eta&&order.eta<today()&&order.stage!==stagesFor(order.transportType).length-1;
 bottom.append(element('span',late?'late':'',order.eta?localDate(order.eta+'T12:00:00Z'):'Без дати'));
 bottom.append(element('span','',order.carrier?'↗ '+order.carrier:'Перевізник не вказаний'));
 open.append(bottom);open.onclick=()=>showDetail(order.id);
 const stage=document.createElement('select');stage.className='card-stage';stage.setAttribute('aria-label','Етап замовлення '+order.name);stage.replaceChildren(...stageOptions(order.transportType));stage.value=String(order.stage);stage.onchange=()=>changeStage(order.id,Number(stage.value));
 card.append(open,stage);
 card.addEventListener('dragstart',e=>{if(e.target.closest('select')){e.preventDefault();return;}dragged=order.id;e.dataTransfer.setData('text/plain',order.id);e.dataTransfer.effectAllowed='move';card.classList.add('dragging');});
 card.addEventListener('dragend',()=>{dragged=null;card.classList.remove('dragging');document.querySelectorAll('.drag-over').forEach(c=>c.classList.remove('drag-over'));});
 return card;
}
function render(){
 $('#total').textContent=orders.length;$('#navCount').textContent=orders.length;
 $('#transit').textContent=orders.filter(o=>['Забір','ПД · Попереднє декларування','Перевезення','Склад у Польщі'].includes(stagesFor(o.transportType)[o.stage])).length;
 $('#customs').textContent=orders.filter(o=>['Митниця','Розмитнення'].includes(stagesFor(o.transportType)[o.stage])).length;
 $('#delivered').textContent=orders.filter(o=>o.stage===stagesFor(o.transportType).length-1).length;
 const filter=$('#countryFilter'),country=filter.value;
 filter.replaceChildren(new Option('Усі країни',''),...[...new Set(orders.map(o=>o.country))].sort((a,b)=>a.localeCompare(b,'uk')).map(c=>new Option(c,c)));
 if([...filter.options].some(o=>o.value===country))filter.value=country;
 const query=$('#search').value.trim().toLocaleLowerCase('uk');
 const visible=orders.filter(o=>(!filter.value||o.country===filter.value)&&(!query||FIELDS.some(f=>o[f].toLocaleLowerCase('uk').includes(query))||reference(o).toLowerCase().includes(query)));
 $('#shown').textContent=visible.length+' папок';
 for(const type of Object.keys(TRANSPORT_TYPES)){
 const board=$('#board-'+type),typed=visible.filter(o=>o.transportType===type);
 board.replaceChildren();board.style.setProperty('--stages',stagesFor(type).length);
 $('#count-'+type).textContent=typed.length+' папок';
 stagesFor(type).forEach((label,i)=>{
  const col=element('section','column'),head=element('div','column-head'),items=typed.filter(o=>o.stage===i);
  head.append(element('span','step-num',String(i+1).padStart(2,'0')),element('span','',label),element('span','col-count',String(items.length)));
  const cards=element('div','cards');items.forEach(o=>cards.append(makeCard(o)));
  const add=element('button','add-column','＋');add.type='button';add.setAttribute('aria-label','Додати замовлення: '+label);add.onclick=()=>openForm(null,i,type);cards.append(add);col.append(head,cards);
  col.addEventListener('dragover',e=>{if(!dragged||orders.find(o=>o.id===dragged)?.transportType!==type)return;e.preventDefault();e.dataTransfer.dropEffect='move';col.classList.add('drag-over');});
  col.addEventListener('dragleave',e=>{if(!col.contains(e.relatedTarget))col.classList.remove('drag-over');});
  col.addEventListener('drop',e=>{e.preventDefault();col.classList.remove('drag-over');if(dragged&&orders.find(o=>o.id===dragged)?.transportType===type&&e.dataTransfer.getData('text/plain')===dragged)changeStage(dragged,i);dragged=null;});
  board.append(col);
 });
 }
 $('#empty').hidden=visible.length>0;
 $('#empty h2').textContent=orders.length?'Нічого не знайдено':'Перший маршрут починається тут';
 $('#empty p').textContent=orders.length?'Змініть пошук або оберіть іншу країну.':'Створіть папку замовлення, додайте виробника й перевізника та відстежуйте доставку до Києва.';
 $('#emptyAdd').hidden=orders.length>0;
}
function showDetail(id,open=true){
 selected=id;const order=orders.find(o=>o.id===id);if(!order)return;
 $('#detailId').textContent=reference(order);$('#detailTitle').textContent=order.name;
 const content=$('#detailContent');content.replaceChildren();
 const stageBox=element('div','detail-stage'),select=document.createElement('select');select.setAttribute('aria-label','Поточний етап');select.replaceChildren(...stageOptions(order.transportType));select.value=String(order.stage);select.onchange=()=>changeStage(id,Number(select.value));stageBox.append(element('span','','Поточний етап'),select);content.append(stageBox);
 const summary=element('div','order-summary');
 const overdue=Boolean(order.eta&&order.eta<today()&&order.stage!==stagesFor(order.transportType).length-1);
 for(const [label,value,isLate] of [
  ['Вага вантажу',order.weight?order.weight+' кг':'Не вказано',false],
  ['Граничний строк поставки',order.eta?localDate(order.eta+'T12:00:00Z'):'Не вказано',overdue]
 ]){
  const metric=element('div','order-metric'+(isLate?' overdue':''));
  metric.append(element('span','metric-label',label),element('strong','metric-value',value));
  if(isLate)metric.append(element('span','deadline-status','Строк поставки минув'));
  summary.append(metric);
 }
 content.append(summary);
 const fields=[['Тип перевезення',TRANSPORT_TYPES[order.transportType]],['Країна відправника',order.country],['Перевізник',order.carrier],['Виробник · точка А',order.manufacturer],['Номер відстеження',order.tracking],['Примітки',order.notes]];
 const grid=element('dl','detail-grid');for(const [label,value]of fields){const wrap=element('div');wrap.append(element('dt','',label),element('dd','',value||'Не вказано'));grid.append(wrap);}content.append(grid);
 const history=element('div','history');history.append(element('strong','','Історія маршруту'));const list=element('ol');for(const h of [...order.history].reverse()){list.append(element('li','',stagesFor(order.transportType)[h.stage]+' · '+new Intl.DateTimeFormat('uk-UA',{dateStyle:'medium',timeStyle:'short',timeZone:'Europe/Kyiv'}).format(new Date(h.at))));}history.append(list);content.append(history);
 if(open)detail.showModal();
}
$('#detailClose').onclick=()=>detail.close();
$('#edit').onclick=()=>{const order=orders.find(o=>o.id===selected);detail.close();if(order)openForm(order);};
$('#delete').onclick=()=>{const order=orders.find(o=>o.id===selected);if(order&&confirm('Видалити папку «'+order.name+'»? Цю дію неможливо скасувати без резервної копії.')&&persist(orders.filter(o=>o.id!==selected))){detail.close();toast('Папку видалено');}};
$('#search').oninput=render;$('#countryFilter').onchange=render;$('#allOrders').onclick=()=>{$('#search').value='';$('#countryFilter').value='';render();};
$('#export').onclick=()=>{
 const blob=new Blob([JSON.stringify({version:1,exportedAt:new Date().toISOString(),orders},null,2)],{type:'application/json'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='artur-logistics-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Резервну копію експортовано');
};
$('#import').onclick=()=>$('#importFile').click();
$('#importFile').onchange=async event=>{
 const file=event.target.files[0];event.target.value='';if(!file)return;
 try{if(file.size>20*1024*1024)throw Error('Файл завеликий. Максимум 20 МБ.');const incoming=parseBackup(await file.text());if(!incoming.length){toast('У копії немає замовлень');return;}if(confirm('Додати '+incoming.length+' папок із резервної копії? Для однакових папок буде збережено новішу версію.')&&persist(mergeOrders(orders,incoming)))toast('Резервну копію імпортовано');}catch(error){toast('Імпорт не виконано: '+error.message);}
};
window.addEventListener('storage',event=>{if(event.key!==STORAGE_KEY)return;try{orders=event.newValue?parseBackup(event.newValue):[];storageBroken=false;render();if(detail.open){if(orders.some(o=>o.id===selected))showDetail(selected,false);else detail.close();}toast('Оновлено з іншої вкладки');}catch{toast('Не вдалося прочитати зміни з іншої вкладки.');}});
render();
