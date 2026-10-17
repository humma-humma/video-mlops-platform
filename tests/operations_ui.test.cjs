const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor(){this.value='';this.textContent='';this.children=[];this.handlers={};}
  append(...items){this.children.push(...items);}
  replaceChildren(){this.children=[];}
  setAttribute(){}
  addEventListener(name,fn){this.handlers[name]=fn;}
  set innerHTML(value){throw new Error('Unsafe HTML rendering');}
}
const settle = async () => {for(let i=0;i<4;i++)await new Promise(setImmediate);};
function harness(fail=false){
  const elements=new Map(),requests=[];
  const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  vm.runInNewContext(fs.readFileSync('src/service/static/operations.js','utf8'), {
    document:{getElementById:get,createElement:()=>new Element(),createElementNS:()=>new Element()},
    AbortSignal,setInterval:()=>1,clearInterval(){},
    fetch:async(path,options)=>{
      requests.push({path,options});
      const value=path==='/metrics'?'model_jobs{deployment="video-summary-v1",status="FAILED"} 3\nvideo_oldest_queued_job_seconds 0':
        path.startsWith('/api/')?[{job_id:'<script>bad</script>',status:'SUCCEEDED',created_at:'today'}]:
        path==='/local/gpu'?{available:true,devices:[{name:'GPU',utilization_percent:43,memory_used_mib:4000,memory_total_mib:8192,temperature_c:82}]}:{status:'ok'};
      return {ok:!fail,status:fail?401:200,json:async()=>value,text:async()=>value};
    }
  });
  return {get,requests};
}
test('dashboard is GET-only, renders job data as text, and shows scoped GPU data',async()=>{
  const h=harness();await settle();
  assert.equal(h.requests.length,4);
  assert.ok(h.requests.every(r=>!r.options.method || r.options.method==='GET'));
  assert.equal(h.get('jobs').children[0].children[0].textContent,'<script>bad</script>');
  assert.match(h.get('gpu').textContent,/43% utilization/);
  assert.equal(h.get('counts').children.length,2);
  h.get('key').value='key';await h.get('refresh').handlers.click();
  assert.equal(h.requests[4].options.headers['X-API-Key'],'key');
});
test('failed refresh clears old readings and distinguishes missing telemetry from zero',async()=>{
  const h=harness(true);await settle();
  assert.match(h.get('health').textContent,/Unavailable: HTTP 401/);
  assert.equal(h.get('gpu').textContent,'Host GPU telemetry unavailable');
  assert.equal(h.get('chart').children.length,0);
  h.get('pause').handlers.click();assert.equal(h.get('state').textContent,'Paused');
});
