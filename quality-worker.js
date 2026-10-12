import {evaluateSelection} from './selection-quality.js?v=quality37';
self.onmessage=event=>{
 try{self.postMessage({report:evaluateSelection(event.data)});}
 catch{self.postMessage({error:true});}
};
