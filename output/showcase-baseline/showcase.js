(() => {
  const root=document.body, lang=root.dataset.language, route=root.dataset.route;
  let timer;
  const notice=()=>{const n=document.getElementById('showcase-notice');n.textContent=root.dataset.notice;n.hidden=false;clearTimeout(timer);timer=setTimeout(()=>n.hidden=true,5000);};
  document.addEventListener('click',e=>{const b=e.target.closest('[data-demo-link]');if(b){e.preventDefault();location.href=b.dataset.demoLink;}});
  document.addEventListener('submit',e=>{
    const f=e.target;e.preventDefault();
    if(f.dataset.demoLanguage){const code=e.submitter?.value;if(['en','zh','hans'].includes(code))location.href='/'+code+route;return;}
    if(f.dataset.demoSearch){const d=new FormData(f),q=String(d.get('q')||'').toLowerCase();
      document.querySelectorAll('.item-card,.wanted-card').forEach(c=>{let show=c.textContent.toLowerCase().includes(q);
        for(const name of ['category','kind']){const v=d.get(name);if(v&&c.dataset[name]!==v)show=false;}
        const p=d.get('price');if(p&&Number(c.dataset.price)>Number(p))show=false;
        const state=d.get('state')||d.get('status');if(state&&state!=='all'&&c.dataset.state!==state)show=false;
        const loc=String(d.get('location')||'').trim().toLowerCase();if(loc&&!String(c.dataset.location||'').toLowerCase().includes(loc))show=false;
        const since=d.get('since');if(since&&c.dataset.start&&Date.parse(c.dataset.start)<Date.parse(since))show=false;
        const when=d.get('when'),days={today:1,week:7,month:30}[when];if(days&&c.dataset.start&&Date.parse(c.dataset.start)>Date.now()+days*86400000)show=false;
        c.hidden=!show;
      });
      const total=[...document.querySelectorAll('.lf-card')].filter(c=>!c.hidden).length;
      const result=document.querySelector('.lf-result-heading .hint');if(result)result.textContent=lang==='en'?`${total} matching notices`:`${total} 则匹配信息`;
      let empty=document.getElementById('demo-empty-results');
      if(!empty&&document.querySelector('.lf-grid')){empty=document.createElement('p');empty.id='demo-empty-results';empty.className='notice';empty.textContent=lang==='en'?'No matching items. Try fewer keywords or another category.':'没有找到符合条件的物品，试试更短的关键词或其他分类。';document.querySelector('.lf-grid').append(empty);}
      if(empty)empty.hidden=total>0;
      return;}
    const link=e.submitter?.dataset.demoLink;if(link){location.href=link;return;}notice();
  });
})();