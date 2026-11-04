// Posts fill in their translation as they scroll into view; chat messages translate when the reader asks.
(function(){
  var copy=document.getElementById('tx-copy');
  var tokenInput=document.querySelector('#lang-form input[name=csrfmiddlewaretoken]');
  if(!copy||!tokenInput)return;
  var text=copy.dataset,lang=document.body.getAttribute('data-language')||'zh';
  var BATCH=12,PREFIX='bbs-tx:',AUTO_KEY='bbs-chat-translate';
  var queue=[],queued={},busy=false,stopped=false,showingOriginal=false;
  var bar=document.querySelector('[data-tx-bar]'),posts={},messages={};

  function store(area,action,key,value){try{return area[action](key,value)}catch(err){return null}}

  // ---- Requests: one at a time, so a long page cannot flood the model.
  function enqueue(ref){if(queued[ref])return;queued[ref]=true;queue.push(ref);flush()}
  function flush(){
    if(busy||stopped||!queue.length)return;
    busy=true;
    var batch=queue.splice(0,BATCH),body=new URLSearchParams();
    batch.forEach(function(ref){body.append('ref',ref)});
    fetch(text.url,{method:'POST',credentials:'same-origin',headers:{'X-CSRFToken':tokenInput.value,'Content-Type':'application/x-www-form-urlencoded'},body:body})
      .then(function(response){return response.json()})
      .then(function(data){
        var done=data.translations||{},retry=data.retry||[];
        Object.keys(done).forEach(function(ref){deliver(ref,done[ref])});
        retry.forEach(function(ref){queue.push(ref)});
        batch.forEach(function(ref){if(!(ref in done)&&retry.indexOf(ref)<0)giveUp(ref)});
        if(data.failed)stop();
      })
      .catch(function(){batch.forEach(giveUp);stop()})
      .then(function(){busy=false;flush()});
  }
  function stop(){stopped=true;queue.splice(0).forEach(giveUp)}
  function giveUp(ref){delete queued[ref];(messages[ref]||[]).forEach(function(button){setButton(button,'idle',text.failed)})}
  function deliver(ref,value){
    delete queued[ref];
    (posts[ref]||[]).forEach(function(el){fillPost(el,value)});
    if(messages[ref]){
      store(sessionStorage,'setItem',PREFIX+lang+':'+ref,value);
      messages[ref].forEach(function(button){showMessage(button,value)});
    }
  }

  // ---- Posts
  function clip(value,max){return max&&value.length>max?value.slice(0,max-1)+'…':value}
  function paint(el){el.textContent=showingOriginal?el.getAttribute('data-tx-original'):el.getAttribute('data-tx-translated')}
  function fillPost(el,value){
    el.setAttribute('data-tx-original',el.textContent);
    el.setAttribute('data-tx-translated',clip(value,Number(el.getAttribute('data-tx-max'))));
    el.removeAttribute('data-tx');
    el.setAttribute('data-tx-machine','');
    paint(el);
    if(bar)bar.hidden=false;
  }
  var waiting=document.querySelectorAll('[data-tx]');
  waiting.forEach(function(el){var ref=el.getAttribute('data-tx');(posts[ref]=posts[ref]||[]).push(el)});
  document.querySelectorAll('[data-tx-machine]').forEach(function(el){el.setAttribute('data-tx-translated',el.textContent)});
  if(bar&&document.querySelector('[data-tx-machine]'))bar.hidden=false;
  if('IntersectionObserver' in window){
    var postObserver=new IntersectionObserver(function(entries){
      entries.forEach(function(entry){if(!entry.isIntersecting)return;postObserver.unobserve(entry.target);enqueue(entry.target.getAttribute('data-tx'))});
    },{rootMargin:'300px'});
    waiting.forEach(function(el){postObserver.observe(el)});
  }else waiting.forEach(function(el){enqueue(el.getAttribute('data-tx'))});
  var toggle=document.querySelector('[data-tx-toggle]');
  if(toggle)toggle.addEventListener('click',function(){
    showingOriginal=!showingOriginal;
    toggle.textContent=showingOriginal?text.showTranslation:text.showOriginal;
    document.querySelectorAll('[data-tx-machine]').forEach(paint);
  });

  // ---- Chat
  var buttons=document.querySelectorAll('[data-tx-msg]');
  var panel=document.querySelector('[data-chat-translate]'),auto=document.getElementById('chat-auto-translate');
  function setButton(button,state,label){button.setAttribute('data-state',state);button.textContent=label;button.disabled=state==='loading'}
  function translationOf(button){return button.parentElement.querySelector('.bubble-translation')}
  function showMessage(button,value){
    var line=translationOf(button);
    if(!line){
      line=document.createElement('p');line.className='bubble-translation';
      button.parentElement.querySelector('p').insertAdjacentElement('afterend',line);
    }
    line.textContent=value;line.hidden=false;
    setButton(button,'shown',text.hide);
  }
  function ask(button){
    var ref=button.getAttribute('data-tx-msg');
    var saved=store(sessionStorage,'getItem',PREFIX+lang+':'+ref);
    if(saved){showMessage(button,saved);return}
    setButton(button,'loading',text.loading);
    stopped=false;
    enqueue(ref);
  }
  function hide(button){
    var line=translationOf(button);
    if(line)line.hidden=true;
    setButton(button,'hidden',text.translate);
  }
  buttons.forEach(function(button){
    var ref=button.getAttribute('data-tx-msg');
    (messages[ref]=messages[ref]||[]).push(button);
    button.setAttribute('data-state','idle');
    button.addEventListener('click',function(){
      if(button.getAttribute('data-state')==='shown')hide(button);
      else ask(button);
    });
  });
  if(panel&&buttons.length){
    panel.hidden=false;
    var chatObserver='IntersectionObserver' in window?new IntersectionObserver(function(entries){
      entries.forEach(function(entry){
        if(!entry.isIntersecting||!auto.checked)return;
        chatObserver.unobserve(entry.target);
        var state=entry.target.getAttribute('data-state');
        if(state==='idle'||state==='hidden')ask(entry.target);
      });
    },{rootMargin:'200px'}):null;
    var applyAuto=function(){
      buttons.forEach(function(button){
        if(!auto.checked){if(button.getAttribute('data-state')==='shown')hide(button);return}
        if(chatObserver)chatObserver.observe(button);
        else ask(button);
      });
    };
    auto.checked=store(localStorage,'getItem',AUTO_KEY)==='1';
    auto.addEventListener('change',function(){store(localStorage,'setItem',AUTO_KEY,auto.checked?'1':'0');applyAuto()});
    if(auto.checked)applyAuto();
  }
  // Signing out leaves nothing readable behind in this tab.
  document.addEventListener('submit',function(event){
    if((event.target.getAttribute('action')||'')!=='/logout/')return;
    try{Object.keys(sessionStorage).forEach(function(key){if(key.indexOf(PREFIX)===0)sessionStorage.removeItem(key)})}catch(err){}
  });
})();
