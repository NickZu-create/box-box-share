/* Payment page: Alipay menu, QR dialog and reference HKD converter. Links still open the QR without JS. */
(() => {
  'use strict';
  const calm=matchMedia('(prefers-reduced-motion: reduce)');
  const buttons=document.querySelector('[data-pay-buttons]');
  const menus=[...document.querySelectorAll('[data-pay-menu]')];
  const closeMenus=except=>{for(const menu of menus)if(menu!==except)menu.open=false;};

  document.addEventListener('click',event=>{closeMenus(menus.find(menu=>menu.contains(event.target)));});
  for(const menu of menus)menu.addEventListener('toggle',()=>{if(menu.open)closeMenus(menu);});
  document.addEventListener('keydown',event=>{
    if(event.key!=='Escape')return;
    const openMenu=menus.find(menu=>menu.open);
    if(openMenu){closeMenus();openMenu.querySelector('summary')?.focus();}
  });

  const dialog=document.querySelector('[data-pay-dialog]');
  if(dialog){
    const image=dialog.querySelector('[data-pay-image]'),frame=dialog.querySelector('[data-pay-frame]');
    const failure=dialog.querySelector('[data-pay-error]'),save=dialog.querySelector('[data-pay-save]');
    let opener=null;
    const setBusy=busy=>{buttons.classList.toggle('is-busy',busy);buttons.setAttribute('aria-busy',String(busy));};
    const finish=()=>{frame.classList.remove('is-loading');setBusy(false);};
    image.addEventListener('load',()=>{image.hidden=false;save.hidden=false;finish();});
    image.addEventListener('error',()=>{if(!image.getAttribute('src'))return;failure.hidden=false;frame.hidden=true;finish();});

    const close=()=>{
      if(!dialog.open||dialog.classList.contains('is-closing'))return;
      let finished=false;
      const done=()=>{if(finished)return;finished=true;dialog.classList.remove('is-closing');dialog.close();image.removeAttribute('src');setBusy(false);opener?.focus();};
      if(calm.matches){done();return;}
      dialog.classList.add('is-closing');
      dialog.addEventListener('animationend',done,{once:true});
      setTimeout(done,300); // Animations can be paused or skipped; the dialog must still close.
    };
    const open=link=>{
      if(buttons.classList.contains('is-busy'))return;
      opener=link.closest('[data-pay-menu]')?.querySelector('summary')||link;
      closeMenus();
      dialog.querySelector('[data-pay-title]').textContent=link.dataset.title;
      failure.hidden=true;frame.hidden=false;image.hidden=true;save.hidden=true;
      frame.classList.add('is-loading');setBusy(true);
      save.href=link.href;image.src=link.href;
      dialog.showModal();
    };
    document.addEventListener('click',event=>{
      const link=event.target.closest('[data-pay-qr]');
      if(!link)return;
      event.preventDefault();open(link);
    });
    dialog.addEventListener('click',event=>{if(event.target===dialog||event.target.closest('[data-pay-close]'))close();});
    dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
  }

  const converter=document.querySelector('[data-pay-converter]');
  if(!converter)return;
  converter.hidden=false;
  const amount=Number(converter.dataset.amount),select=converter.querySelector('select');
  const output=converter.querySelector('[data-pay-converted]'),rateLine=converter.querySelector('[data-pay-rate]');
  const lang=document.documentElement.lang;
  const money=(value,currency)=>new Intl.NumberFormat(lang,{style:'currency',currency}).format(value);
  let rates=null,updated=null,shown=0,frameId=0;
  const animateTo=(value,currency)=>{
    cancelAnimationFrame(frameId);
    if(calm.matches||!shown){shown=value;output.textContent=money(value,currency);return;}
    const from=shown,started=performance.now();
    const step=now=>{
      const progress=Math.min((now-started)/320,1),eased=1-(1-progress)**3;
      shown=from+(value-from)*eased;output.textContent=money(shown,currency);
      if(progress<1)frameId=requestAnimationFrame(step);
    };
    frameId=requestAnimationFrame(step);
  };
  const render=()=>{
    const currency=select.value,rate=Number(rates[currency]);
    if(!Number.isFinite(rate)||rate<=0||!Number.isFinite(amount*rate)){fail();return;}
    animateTo(amount*rate,currency);
    const parts=[];
    if(currency!=='HKD')parts.push(`1 HKD = ${rates[currency]} ${currency}`);
    if(updated)parts.push(`${converter.dataset.updated} ${new Intl.DateTimeFormat(lang,{timeZone:'Asia/Hong_Kong',dateStyle:'medium',timeStyle:'short'}).format(updated*1000)}`);
    rateLine.textContent=parts.join(' · ');
  };
  const fail=()=>{converter.classList.remove('is-loading');converter.classList.add('is-failed');output.textContent='—';rateLine.textContent=converter.dataset.failed;};
  select.addEventListener('change',render);

  const options=[...select.options].map(option=>option.value);
  select.value=options.find(currency=>currency!=='HKD')||'HKD';
  if(options.length===1&&options[0]==='HKD'){
    rates={HKD:'1'};converter.classList.remove('is-loading');render();
    return;
  }
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  fetch(converter.dataset.ratesUrl,{signal:controller.signal,credentials:'same-origin',headers:{Accept:'application/json'}})
    .then(response=>{if(!response.ok)throw new Error(response.status);return response.json();})
    .then(data=>{rates=data.rates;updated=data.updated;converter.classList.remove('is-loading');select.disabled=false;render();})
    .catch(fail)
    .finally(()=>clearTimeout(timer));
})();
