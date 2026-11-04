/* Presentation controls operate only on the local synthetic document. */
(() => {
  'use strict';
  const lang=document.body.dataset.language;
  const text=(h,z,e)=>lang==='en'?e:lang==='zh'?z:h;
  function chips(){
    const form=document.querySelector('.filter-form[data-filter]'),rail=document.querySelector('.applied-filters');
    if(!form||!rail)return;
    rail.replaceChildren();
    const values=new FormData(form);
    for(const name of ['q','category','price','kind','when','state','start']){
      const value=String(values.get(name)||'').trim();
      if(!value||(name==='state'&&value==='open'))continue;
      const field=form.elements.namedItem(name);
      let label=field.tagName==='SELECT'?field.selectedOptions[0]?.textContent:value;
      if(name==='price')label=(form.dataset.filter==='wanted'?text('总预算 ≤ HK$ ','總預算 ≤ HK$ ','Total ≤ HK$ '):text('日租 ≤ HK$ ','日租 ≤ HK$ ','Daily ≤ HK$ '))+value;
      if(name==='start')label=value.replace('T',' ')+(values.get('end')?' – '+String(values.get('end')).replace('T',' '):'');
      const button=document.createElement('button');button.type='button';button.dataset.removeFilter=name;
      button.setAttribute('aria-label',text('移除筛选：','移除篩選：','Remove filter: ')+label);
      const span=document.createElement('span');span.textContent=label;button.append(span);
      const x=document.createElement('span');x.className='chip-remove';x.textContent='×';x.setAttribute('aria-hidden','true');button.append(x);rail.append(button);
    }
    rail.hidden=!rail.childElementCount;
  }
  function searchThreads(input){
    const q=input.value.trim().toLocaleLowerCase();let count=0;
    document.querySelectorAll('.thread-row').forEach(row=>{row.hidden=!row.textContent.toLocaleLowerCase().includes(q);if(!row.hidden)count++;});
    const status=document.querySelector('.thread-search-status');
    if(status){status.hidden=!q;status.textContent=count?count+text(' 个对话',' 個對話',' conversations'):text('没有匹配的对话。试试姓名或物品名称。','沒有符合的對話。試試姓名或物品名稱。','No matching conversations. Try a person or item name.');}
  }
  document.addEventListener('DOMContentLoaded',chips);
  document.addEventListener('collection:mounted',chips);
  document.addEventListener('input',e=>{if(e.target.matches('[data-thread-search]'))searchThreads(e.target);});
  document.addEventListener('search',e=>{if(e.target.matches('[data-thread-search]'))searchThreads(e.target);},true);
  document.addEventListener('submit',e=>{
    if(!e.target.matches('.filter-form[data-filter]'))return;
    chips();const form=e.target;
    form.querySelectorAll('[aria-invalid]').forEach(n=>n.removeAttribute('aria-invalid'));
    const status=document.querySelector('#filter-status');
    if(status?.dataset.state==='error'){
      const price=form.elements.namedItem('price');
      const target=price&&(price.validity.badInput||Number(price.value)<0)?price:form.elements.namedItem('start');
      if(target){target.setAttribute('aria-invalid','true');target.focus();}
    }
  });
  document.addEventListener('reset',()=>setTimeout(chips,0));
  document.addEventListener('click',e=>{
    const chip=e.target.closest('[data-remove-filter]');
    if(chip){const form=document.querySelector('.filter-form[data-filter]');const key=chip.dataset.removeFilter;for(const name of key==='start'?['start','end']:[key]){const field=form.elements.namedItem(name);if(field)field.value=name==='state'?'open':'';}form.requestSubmit();form.elements.namedItem('q')?.focus();}
    const state=e.target.closest('[data-order-state]');
    if(state){let count=0;document.querySelectorAll('[data-order-state]').forEach(b=>b.setAttribute('aria-pressed',String(b===state)));document.querySelectorAll('[data-order-status]').forEach(row=>{row.hidden=state.dataset.orderState!=='all'&&row.dataset.orderStatus!==state.dataset.orderState;if(!row.hidden)count++;});const empty=document.querySelector('.order-filter-status');if(empty)empty.hidden=count>0;}
    document.querySelectorAll('.lang-menu[open],.more-menu[open]').forEach(menu=>{if(!menu.contains(e.target))menu.open=false;});
  });
  document.addEventListener('keydown',e=>{if(e.key==='Escape')document.querySelectorAll('.lang-menu[open],.more-menu[open]').forEach(menu=>{menu.open=false;menu.querySelector('summary')?.focus();});});
})();
