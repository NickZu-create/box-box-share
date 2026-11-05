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
    const actions=dialog.querySelector('[data-pay-actions]'),store=actions.querySelector('[data-pay-store]');
    const direct=actions.querySelector('[data-pay-direct]'),launch=actions.querySelector('[data-pay-launch]');
    const steps=actions.querySelector('[data-pay-steps]'),missing=actions.querySelector('[data-pay-missing]');
    const desktopHint=dialog.querySelector('[data-pay-desktop]');
    const ua=navigator.userAgent;
    const ios=/iPhone|iPad|iPod/.test(ua)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
    const android=/Android/.test(ua);
    const inApp={wechat:/MicroMessenger/i.test(ua),alipay_cn:/AlipayClient/i.test(ua)};
    // Only links with a documented or long-established form. Alipay HK and FPS have none we could verify,
    // and FPS has no single app, so those two stop at saving the code.
    const APP_LINKS={wechat:'weixin://',alipay_cn:'alipays://platformapi/startApp?appId=10000007'};
    // The decoded code is only ever passed on if it is plainly an Alipay collection code.
    const ALIPAY_CODE=/^https:\/\/qr\.alipay\.com\/[A-Za-z0-9_-]+$/i;
    let opener=null,picture=null,request=0,missingTimer=0;

    const readCode=async blob=>{
      // Read on the phone itself: the image never leaves it. The browser's own detector if it has one
      // (Android Chrome), otherwise jsQR, which is what makes this work on an iPhone.
      if(typeof createImageBitmap!=='function')return '';
      const bitmap=await createImageBitmap(blob);
      if('BarcodeDetector' in window){
        const found=await new BarcodeDetector({formats:['qr_code']}).detect(bitmap).catch(()=>[]);
        if(found.length)return found[0].rawValue.trim();
      }
      if(typeof jsQR!=='function')return '';
      const scale=Math.min(1,1000/Math.max(bitmap.width,bitmap.height));
      const canvas=document.createElement('canvas');
      canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);
      const context=canvas.getContext('2d',{willReadFrequently:true});
      context.drawImage(bitmap,0,0,canvas.width,canvas.height);
      const found=jsQR(context.getImageData(0,0,canvas.width,canvas.height).data,canvas.width,canvas.height);
      return found?found.data.trim():'';
    };
    // Phones only allow saving and sharing during the tap itself, so everything is ready before it.
    const mobile=ios||android,inAnyApp=inApp.wechat||inApp.alipay_cn,ready=new Map();
    const load=async link=>{
      const response=await fetch(link.href,{credentials:'same-origin'});
      if(!response.ok)throw new Error(String(response.status));
      const blob=await response.blob(),channel=link.dataset.channel;
      const entry={file:new File([blob],`box-box-share-${channel}-qr.jpg`,{type:'image/jpeg'}),direct:''};
      if(channel==='alipay_cn'&&!inApp.alipay_cn){
        const code=await readCode(blob).catch(()=>'');
        if(ALIPAY_CODE.test(code))entry.direct=`${APP_LINKS.alipay_cn}&actionType=route&qrcode=${encodeURIComponent(code)}`;
      }
      return entry;
    };
    if(mobile)for(const link of document.querySelectorAll('[data-pay-qr]')){
      const slot={};
      slot.loading=load(link).then(entry=>Object.assign(slot,entry)).catch(()=>{});
      ready.set(link.href,slot);
    }
    const useEntry=entry=>{
      picture=entry.file;
      store.disabled=false;
      if(!entry.direct)return;
      direct.href=entry.direct;
      direct.hidden=false;
      // Paying directly needs no saved image: saving stays as the quiet fallback.
      launch.hidden=true;
      store.textContent=store.dataset.label;
      steps.textContent=actions.dataset.stepsDirect;
    };
    const watchLeaving=()=>{
      // If the page is still in front shortly after the jump, the app probably did not open.
      clearTimeout(missingTimer);
      missing.hidden=true;
      missingTimer=setTimeout(()=>{if(!document.hidden&&dialog.open)missing.hidden=false;},1800);
    };
    document.addEventListener('visibilitychange',()=>{if(document.hidden)clearTimeout(missingTimer);});
    direct.addEventListener('click',watchLeaving);
    launch.addEventListener('click',watchLeaving);
    const saveAndGo=()=>{
      if(!picture)return;
      if(ios&&navigator.canShare&&navigator.canShare({files:[picture]})){
        // The iPhone share sheet is the only way to the photo library; the person picks "Save Image".
        // Its promise may never settle, so nothing waits for it, and only the file is shared.
        navigator.share({files:[picture]}).catch(()=>{});
      }else{
        const url=URL.createObjectURL(picture),anchor=document.createElement('a');
        anchor.href=url;anchor.download=picture.name;document.body.append(anchor);anchor.click();anchor.remove();
        setTimeout(()=>URL.revokeObjectURL(url),10000);
        if(android&&!launch.hidden)setTimeout(()=>{watchLeaving();location.href=launch.href;},500);
      }
    };
    store.addEventListener('click',saveAndGo);
    const showActions=(link,ticket)=>{
      const channel=link.dataset.channel;
      actions.hidden=!mobile;desktopHint.hidden=mobile;save.classList.toggle('pay-save-desktop',mobile);
      if(!mobile)return;
      picture=null;store.disabled=true;direct.hidden=true;missing.hidden=true;
      const appLink=inApp[channel]?'':APP_LINKS[channel]||'';
      launch.hidden=!appLink;
      if(appLink){launch.href=appLink;launch.textContent=actions.getAttribute(`data-open-${channel}`);}
      steps.textContent=inAnyApp?actions.dataset.stepsInapp:actions.getAttribute(`data-steps-${channel}`);
      store.textContent=android&&appLink?actions.getAttribute(`data-save-open-${channel}`):store.dataset.label;
      const slot=ready.get(link.href);
      if(slot&&slot.file){
        useEntry(slot);
        // One tap is enough: straight into Alipay where possible, otherwise save and open the app.
        // Inside an app's own browser long-press recognition is quicker, and saving is often blocked there.
        if(inAnyApp)return;
        if(slot.direct){watchLeaving();location.href=slot.direct;}
        else saveAndGo();
      }else if(slot)slot.loading.then(()=>{if(ticket===request&&slot.file)useEntry(slot);});
    };
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
      dialog.dataset.channel=link.dataset.channel;
      const chosen=document.querySelector('[data-pay-total]')?.dataset.final;
      if(chosen)dialog.querySelector('[data-pay-amount]').textContent=chosen;
      failure.hidden=true;frame.hidden=false;image.hidden=true;save.hidden=true;
      frame.classList.add('is-loading');setBusy(true);
      save.href=link.href;image.src=link.href;
      request+=1;showActions(link,request);
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
  const total=document.querySelector('[data-pay-total]'),rateLine=converter.querySelector('[data-pay-rate]');
  const lang=document.documentElement.lang;
  // The code is always written out: the yen and yuan signs alone cannot be told apart.
  const money=(value,currency)=>{
    const digits=new Intl.NumberFormat('en',{style:'currency',currency}).resolvedOptions().maximumFractionDigits;
    const number=new Intl.NumberFormat('en',{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(value);
    return `${currency==='HKD'?'HK$':currency} ${number}`;
  };
  let rates=null,updated=null,shown=amount,frameId=0;
  const animateTo=(value,currency,sameCurrency)=>{
    cancelAnimationFrame(frameId);
    if(calm.matches||!sameCurrency){shown=value;total.textContent=money(value,currency);return;}
    const from=shown,started=performance.now();
    const step=now=>{
      const progress=Math.min((now-started)/320,1),eased=1-(1-progress)**3;
      shown=from+(value-from)*eased;total.textContent=money(shown,currency);
      if(progress<1)frameId=requestAnimationFrame(step);else total.textContent=money(value,currency);
    };
    frameId=requestAnimationFrame(step);
  };
  const render=()=>{
    const currency=select.value,rate=Number(rates[currency]);
    if(!Number.isFinite(rate)||rate<=0||!Number.isFinite(amount*rate)){fail();return;}
    const value=amount*rate;
    // The pop-up reads this, so it can only ever show the amount chosen here.
    total.dataset.final=money(value,currency);
    animateTo(value,currency,false);
    const parts=[];
    if(currency!=='HKD')parts.push(`1 HKD = ${rates[currency]} ${currency}`);
    if(updated)parts.push(`${converter.dataset.updated} ${new Intl.DateTimeFormat(lang,{timeZone:'Asia/Hong_Kong',dateStyle:'medium',timeStyle:'short'}).format(updated*1000)}`);
    rateLine.textContent=parts.join(' · ');
  };
  const fail=()=>{
    // Without a rate only HKD is honest, so the choice goes back to it and is locked.
    converter.classList.remove('is-loading');converter.classList.add('is-failed');
    select.value='HKD';select.disabled=true;
    total.dataset.final=money(amount,'HKD');total.textContent=total.dataset.final;
    rateLine.textContent=converter.dataset.failed;
  };
  select.addEventListener('change',render);
  select.value='HKD';
  total.dataset.final=money(amount,'HKD');total.textContent=total.dataset.final;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  fetch(converter.dataset.ratesUrl,{signal:controller.signal,credentials:'same-origin',headers:{Accept:'application/json'}})
    .then(response=>{if(!response.ok)throw new Error(response.status);return response.json();})
    .then(data=>{rates=data.rates;updated=data.updated;converter.classList.remove('is-loading');select.disabled=false;render();})
    .catch(fail)
    .finally(()=>clearTimeout(timer));
})();
