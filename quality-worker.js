import {evaluateSelection} from './selection-quality.js?v=quality49';
self.onmessage=event=>{
 try{self.postMessage({report:evaluateSelection(Array.isArray(event.data)?event.data:event.data.rows,Array.isArray(event.data)?undefined:event.data.interests)});}
 catch{self.postMessage({error:true});}
};
