"""Presentation-only marketplace flows. No product database or real accounts."""
import json,re
from pathlib import Path
from copy import deepcopy
from bs4 import BeautifulSoup as B

COPY={
 'login':('演示登录','Demo sign in'),'logout':('退出演示登录','Sign out of demo'),'guest':('游客','Guest'),'member':('Demo 已登录','Signed in as Demo'),
 'sandbox':('交互展示版 · 仅当前标签页演示，不连接真实账号、消息或交易','Interactive demo · This tab only. No real accounts, messages or transactions'),
 'reset':('重置演示','Reset demo'),'loginTitle':('登录后继续','Sign in to continue'),'loginBody':('使用 Demo 身份体验，确认后回到当前物品继续操作。不需要邮箱或密码。','Continue as Demo and return to this item. No email or password is needed.'),
 'continue':('以 Demo 身份继续','Continue as Demo'),'cancel':('取消','Cancel'),'close':('关闭','Close'),'buy':('直接购买','Buy now'),'contact':('私信沟通','Message seller'),
 'confirmBuy':('确认购买','Confirm purchase'),'buyBody':('确认后生成“待交接”的示例订单。此演示不会扣款，也不会自动完成交易。','Create a sample order awaiting handover. No payment is taken and the transaction is not marked completed.'),
 'pending':('待交接 · 示例订单','Awaiting handover · Sample order'),'pendingRent':('待物主确认 · 示例申请','Awaiting owner approval · Sample request'),
 'viewOrder':('查看示例订单','View sample order'),'message':('进入 Messages 沟通','Continue in Messages'),'share':('分享物品','Share item'),'shareHelp':('打开链接即可浏览此物品，购买或申请时再登录。','Anyone with this link can view the item. Sign in when buying or requesting.'),
 'copy':('复制链接','Copy link'),'copied':('链接已复制','Link copied'),'copyManual':('请选中下方链接并复制。','Select and copy the link below.'),'systemShare':('系统分享／微信','Device share / WeChat'),
 'shareFallback':('此浏览器无法调起系统分享。可复制链接，在微信中粘贴发送。','Device sharing is unavailable here. Copy the link and paste it into WeChat.'),
 'shareNote':('微信等可用应用由设备决定；也可以复制链接发送。','Available apps depend on your device. You can always copy the link.'),
 'rent':('租借','Rent / borrow'),'sale':('出售','For sale'),'borrow':('求借','Want to borrow'),'wantedBuy':('求购','Want to buy'),'all':('全部','All'),
 'amountLimit':('金额上限（HKD）','Price limit (HKD)'),'mixedPrice':('租借按日租金，出售按一次性售价筛选。','Rental prices are per day; sale prices are one-off totals.'),
 'send':('发送消息','Send message'),'reply':('模拟对方回复','Simulate reply'),'replyBody':('好的，我们可以约在校园公共地点交接。（对方示例回复）','Sounds good. We can meet at a public place on campus. (Simulated reply)'),
 'replyNote':('演示工具：自行发送消息或模拟对方回复，体验联系方式解锁。','Demo controls: send a message or simulate a reply to test contact access.'),
 'contacts':('联系方式','Contact details'),'contactRule':('同一对话满 4 条消息，且双方都至少发过 1 条后可见。','Visible after 4 messages in this conversation, with at least one from each person.'),
 'needPeer':('还需要双方都参与聊天。','Both people must participate.'),'loginContacts':('登录后才能解锁联系方式。','Sign in before unlocking contact details.'),
 'blockedContacts':('已拉黑，联系方式不可见。','Contact details are hidden for a blocked conversation.'),'sampleContacts':('以下为虚构联系方式，不代表真实账号。','These are fictional contact details, not real accounts.'),
 'saved':('已保存在当前标签页的演示状态中。','Saved to this tab’s demo state.'),'published':('查看发布预览','View listing preview'),'publish':('生成发布预览','Preview listing'),
 'saleTitle':('闲置计算器 · 出售示例','Spare calculator · Sale example'),'saleDescription':('功能正常的闲置计算器，附保护盖。可在校园交接。这是出售功能的合成示例。','A working spare calculator with its cover. Campus handover. This is a synthetic sale example.'),
 'buyTitle':('求购二手课本 · 示例','Looking for a used textbook · Example'),'buyDescription':('想买一本二手课本，请私信沟通版本和交接地点。这是合成求购示例。','Looking to buy a used textbook. Message to discuss the edition and handover. Synthetic example.'),
 'itemName':('物品名称','Item name'),'description':('描述','Description'),'price':('金额（HKD）','Amount (HKD)'),'daily':('每日租金（HKD）','Daily price (HKD)'),'budget':('总预算（HKD）','Total budget (HKD)'),
 'invalid':('请填写金额和描述；金额不能为负数。','Enter an amount and description. The amount cannot be negative.'),'invalidDates':('结束时间必须晚于开始时间。','The end time must be after the start time.'),
 'unavailable':('此演示物品已生成购买订单，请先查看订单。','A sample purchase already exists for this item. View the order first.'),'emptyDraft':('这里还没有发布预览。','No listing preview is available here yet.'),
 'browse':('浏览物品','Explore items'),'noOrder':('这里还没有示例订单。','No sample order is available here yet.'),'confirmRequest':('确认提交示例申请','Confirm sample request'),
 'requestBody':('物主接受后再安排交接。此处只演示流程，不占用真实库存。','Arrange handover after owner approval. This demo does not reserve real inventory.'),
 'amount':('金额','Amount'),'deposit':('押金','Deposit'),'date':('日期','Dates'),'location':('交接地点','Handover location'),'submitRequest':('提交租借申请','Request to borrow'),
 'free':('免费借用','Free to borrow'),'perDay':('／日','/ day'),'generatedTitle':('从描述首句生成，可展开修改','Generated from the first sentence; you can edit it'),
 'unlocked':('联系方式已解锁','Contact details unlocked'),'progress':('条消息','messages'),'whatsapp':('WhatsApp','WhatsApp'),'phone':('电话','Phone'),'wechat':('WeChat','WeChat'),'instagram':('Instagram','Instagram'),
 'profileNote':('仅在当前标签页保存示例资料。请勿填写真实隐私信息；联系方式不会放在公开主页上。','Example profile saved in this tab only. Do not enter real private details. Contact information is not shown on the public profile.'),
 'optional':('可选','Optional'),'oneOff':('一次性售价','One-off price'),'offer':('私信提供物品','Message an offer'),'remaining':('借用流程需物主确认；购买示例等待交接。','Borrowing needs owner approval; sample purchases await handover.'),
 'resetTitle':('重置当前标签页的演示？','Reset this tab’s demo?'),'resetBody':('会清除本标签页的演示登录、发布预览、示例消息和订单。网站原有示例不受影响。','Clears this tab’s demo sign-in, drafts, messages and orders. Original examples remain available.'),
 'resetConfirm':('确认重置','Reset demo'),'storageError':('浏览器无法保存演示状态，本次操作未保存。','Demo state could not be saved in this browser. This action was not saved.'),
 'outsideWindow':('所选日期超出示例可借窗口或最长借期，请修改日期。','The dates exceed this sample availability window or maximum duration.'),
}

def frag(html):return B(html,'html.parser')

def publish_form(lang,tr,ico,wanted=False):
 t=lambda z,e:tr(lang,z,e)
 kind='wanted' if wanted else 'item'
 cat=[('tech',t('电子器材','Tech')),('study',t('学习用品','Study')),('outdoor',t('户外运动','Outdoors')),('home',t('生活用品','Living')),('creative',t('创作音乐','Creative')),('other',t('其他','Other'))]
 return f'''<section class="page narrow market-page"><a class="breadcrumb" href="/{lang}/{'seeking/' if wanted else ''}">{ico('arrow-left')}{t('返回浏览','Back to browse')}</a>
 <div class="market-heading"><span class="eyebrow">BOX BOX SHARE</span><h1>{t('发布需求' if wanted else '发布物品','Post a request' if wanted else 'List an item')}</h1><p>{t('日期和常用条件已填好，按需要修改。','Dates and common settings are filled in. Change them as needed.')}</p></div>
 <form class="panel market-form" data-market-publish="{kind}" novalidate>
 <fieldset class="intent-picker"><legend>{t('我想','I want to')}</legend><label><input type="radio" name="intent" value="{'borrow' if wanted else 'rent'}" checked>{t('求借' if wanted else '借出／出租','Borrow' if wanted else 'Lend / rent out')}</label><label><input type="radio" name="intent" value="{'buy' if wanted else 'sale'}">{t('求购' if wanted else '出售','Buy' if wanted else 'Sell')}</label></fieldset>
 <p class="market-mode-note" data-mode-note></p>
 <div class="market-required"><label><span data-amount-label>{t('总预算（HKD）' if wanted else '每日租金（HKD）','Total budget (HKD)' if wanted else 'Daily price (HKD)')}</span><input name="amount" type="number" min="0" step="0.01" inputmode="decimal" required placeholder="0.00"></label>
 <label>{t('描述','Description')}<textarea name="description" rows="4" maxlength="2000" required placeholder="{t('写清物品、状况和你的需求…','Describe the item, condition and what you need…')}"></textarea></label></div>
 <details class="publish-options"><summary>{t('名称、照片与其他条件（可选）','Name, photo and other settings (optional)')}{ico('chevron-down')}</summary><div class="publish-options-grid">
 <label>{t('物品名称','Item name')}<input name="title" maxlength="100" placeholder="{t('从描述首句自动生成','Generated from the first sentence')}"></label>
 <label>{t('分类','Category')}<select name="category">{''.join(f'<option value="{v}"'+(' selected' if v=='other' else '')+f'>{label}</option>' for v,label in cat)}</select></label>
 <label>{t('交接地点','Handover location')}<input name="location" value="CityUHK campus" maxlength="160"></label>
 <label data-rental-only>{t('物品状况','Condition')}<input name="condition" value="{t('使用状况良好','Good condition')}" maxlength="200"></label>
 <label data-rental-only>{t('开始时间（香港）','Start (Hong Kong)')}<input name="start" type="datetime-local"></label><label data-rental-only>{t('结束时间（香港）','End (Hong Kong)')}<input name="end" type="datetime-local"></label>
 {'' if wanted else '<label data-rental-only>'+t('押金（HKD）','Deposit (HKD)')+'<input name="deposit" type="number" min="0" step="0.01" value="0"></label><label data-rental-only>'+t('最长借用天数','Maximum days')+'<input name="maxDays" type="number" min="1" value="7"></label>'}
 <label class="photo-field">{t('照片 · 本地预览','Photo · local preview')}<input name="photo" type="file" accept="image/jpeg,image/png,image/webp"><img data-photo-preview hidden alt="{t('本地照片预览','Local photo preview')}"></label>
 </div></details><p class="market-form-status" role="status"></p><div class="market-form-footer"><span data-title-preview class="hint"></span><button class="button" type="submit">{t('生成发布预览','Preview listing')}{ico('arrow-up-right')}</button></div>
 <p class="hint">{t('这是演示发布，仅当前标签页保留，不会上架到真实平台。','Demo only. Kept in this tab, not posted to the real platform.')}</p></form></section>'''

def decorate(s,lang,route,tr,ico):
 t=lambda z,e:tr(lang,z,e)
 s.body['class']=s.body.get('class',[])+['market-demo']
 s.body['data-demo-route']=route
 # Shared sandbox UI makes the simulated identity explicit without credentials.
 strip=s.select_one('.demo-strip')
 if strip:
  strip.clear();strip.append(frag('<span>'+t(*COPY['sandbox'])+'</span><span class="demo-identity" data-demo-identity></span><button type="button" data-market-auth>'+t(*COPY['login'])+'</button><button type="button" data-market-reset>'+t(*COPY['reset'])+'</button>'))
 if route in ('items/new/','wanted/new/'):
  s.main.clear();s.main.append(frag(publish_form(lang,tr,ico,route.startswith('wanted'))))
 for tile in s.select('.item-tile'):
  tile['data-intent']='rent';link=tile.select_one('.tile-link')
  if link:
   tile['class']=tile.get('class',[])+['shareable-item']
   tile.append(frag(f'<button class="item-share" type="button" data-share-item="{link["href"]}" aria-label="{t(*COPY["share"])}">{ico("share-2")}</button>'))
 for tile in s.select('.wanted-tile'):tile['data-intent']='borrow'
 form=s.select_one('.filter-form[data-filter]')
 if form and form.get('data-filter') in ('items','wanted'):
  wanted=form['data-filter']=='wanted';form.append(frag('<input name="intent" type="hidden" value="">'))
  toolbar=s.select_one('.explore-toolbar')
  if toolbar:
   modes=[('',t(*COPY['all'])),('borrow' if wanted else 'rent',t(*COPY['borrow'] if wanted else COPY['rent'])),('buy' if wanted else 'sale',t(*COPY['wantedBuy'] if wanted else COPY['sale']))]
   toolbar.insert_after(frag('<div class="market-filter-tabs" role="group" aria-label="'+t('交易类型','Listing type')+'">'+''.join('<button type="button" data-market-filter="'+value+'" aria-pressed="'+str(not bool(value)).lower()+'">'+label+'</button>' for value,label in modes)+'</div>'))
 if re.fullmatch(r'items/\d+/',route):
  s.body['data-item-id']=route.strip('/').split('/')[-1]
  decision=s.select_one('.item-decision')
  if decision:
   forms=decision.select('form')
   for form in forms:
    if form.select_one('input[name=start]'):
     form['data-market-rental']='true'
     if not form.select_one('[name=end]'):continue
     old=form.select_one('button');old.string=t('预览租借费用','Preview rental cost');old['name']='';old['type']='button';old['data-market-quote']='true'
     form.append(frag('<div class="rental-quote" role="status" hidden></div><button class="button" type="submit">'+t(*COPY['submitRequest'])+'</button>'))
   page=s.select_one('main .page')
   page.insert(1,frag(f'<button class="detail-share" type="button" data-share-item="/{lang}/{route}" aria-label="{t(*COPY["share"])}">{ico("share-2")}</button>'))
   price=s.select_one('.price');owner=s.select_one('.owner-box')
   s.body['data-item-price']=re.search(r'\d+(?:\.\d+)?',price.get_text()).group() if price and re.search(r'\d+(?:\.\d+)?',price.get_text()) else '0'
   s.body['data-item-deposit']='0' if route=='items/2/' else '100'
   dates=re.findall(r'\d{4}-\d\d-\d\d \d\d:\d\d',s.main.get_text(' ',strip=True))[:2]
   if len(dates)==2:s.body['data-item-start']=dates[0].replace(' ','T');s.body['data-item-end']=dates[1].replace(' ','T')
   s.body['data-item-max']='14'
   for label in s.select('dt'):
    if label.get_text(strip=True) in ('交接地点','交接地點','Handover location','Location'):
     value=label.find_next_sibling('dd')
     if value:s.body['data-item-location']=value.get_text(strip=True)
   if owner:s.body['data-item-owner']=owner['href'].rstrip('/').split('/')[-1]
   else:s.body['data-item-owner']='1'
   s.body['data-item-peer']=owner.select_one('strong').get_text(strip=True) if owner and owner.select_one('strong') else 'Jamie'
   for contact in decision.select('[data-demo-link]'):contact['data-market-contact-item']='true'
 if re.fullmatch(r'wanted/\d+/',route):
  for form in s.select('main form[data-demo-action]'):form['data-market-guard']='true'
 if route=='profile/':
  form=s.select_one('main form');form['data-market-profile']='true'
  fields='<fieldset class="profile-contacts"><legend>'+t(*COPY['contacts'])+'</legend><p class="hint">'+t(*COPY['profileNote'])+'</p>'
  for key in ('whatsapp','phone','wechat','instagram'):
   fields+='<label>'+t(*COPY[key])+' · '+t(*COPY['optional'])+f'<input name="contact_{key}" maxlength="80" autocomplete="off" placeholder="'+t('仅填写虚构示例','Fictional example only')+'"></label>'
  fields+='<p class="contact-rule">'+t(*COPY['contactRule'])+'</p></fieldset>'
  form.select_one('.actions').insert_before(frag(fields))
  form.append(frag('<p class="market-profile-status" role="status"></p>'))
 if re.fullmatch(r'messages/\d+/',route):
  s.body['data-conversation']=route.strip('/').split('/')[-1]
  s.body['data-peer']=s.select_one('.chat-heading h2').get_text(strip=True)
  s.body['data-blocked']='true' if not s.select_one('.chat-composer') else 'false'
  composer=s.select_one('.chat-composer')
  if composer:composer['data-market-message']='true'
  if s.select_one('.chat-header'):
   s.select_one('.chat-header').append(frag('<div class="contact-gate" data-contact-gate></div>'))
   if composer:composer.insert_after(frag('<div class="demo-reply-tools"><span>'+t(*COPY['replyNote'])+'</span><button type="button" data-market-reply>'+t(*COPY['reply'])+'</button></div>'))
 for anchor in s.select('a[href]'):
  href=anchor['href']
  if re.search(r'/messages/\d+/$',href) and not anchor.find_parent(class_='thread-list'):
   anchor['data-market-contact']='true'
 # Capturing handlers must own these forms before legacy demo notices run.
 strings=re.findall(r"'([^'\n]*)'",(Path(__file__).parent/'design-preview/market-demo.js').read_text(encoding='utf8'))
 dictionary={k:t(*v) for k,v in COPY.items()}
 dictionary['_traditional']={value:tr(lang,value,value) for value in strings if re.search(r'[\u4e00-\u9fff]',value)} if lang=='zh' else {}
 s.body.append(frag('<script type="application/json" id="market-copy">'+json.dumps(dictionary,ensure_ascii=False).replace('<','\\u003c')+'</script>'))

def finalize(out,tr,ico,version):
 """Add explicit synthetic examples, never change an existing record's mode."""
 for lang in ('hans','zh','en'):
  t=lambda z,e:tr(lang,z,e)
  def read(rel):return B((out/lang/rel/'index.html').read_text(encoding='utf8'),'html.parser')
  def save(s,rel):
   p=out/lang/rel/'index.html';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(str(s),encoding='utf8')
  # A dedicated sale example uses an existing illustration-free item component.
  home=read('');grid=home.select_one('.item-grid');sample=deepcopy(grid.select_one('.item-tile'))
  sample['data-intent']='sale';sample['data-demo-example']='sale';sample['data-price']='80';sample['data-category']='study';sample['data-search']=t(*COPY['saleTitle'])+' '+t(*COPY['saleDescription'])
  sample.select_one('.tile-link')['href']=f'/{lang}/items/sale-example/'
  sample.select_one('.tile-title').string=t(*COPY['saleTitle']);sample.select_one('.tile-title')['title']=t(*COPY['saleTitle']);sample.select_one('.tile-price').clear();sample.select_one('.tile-price').string='HK$ 80'
  sample.select_one('.tile-category').string=t(*COPY['sale']);sample.select_one('.tile-dates').string=t(*COPY['oneOff'])
  sample.select_one('.item-share')['data-share-item']=f'/{lang}/items/sale-example/'
  sample.select_one('.tile-footer').clear();sample.select_one('.tile-footer').string='Jamie · '+t('出售示例','Sale example')
  grid.insert(0,sample);save(home,'')
  seek=read('seeking');sample=deepcopy(seek.select_one('.wanted-tile'));sample['href']=f'/{lang}/wanted/buy-example/'
  sample['data-intent']='buy';sample['data-price']='100';sample['data-category']='study';sample['data-search']=t(*COPY['buyTitle'])+' '+t(*COPY['buyDescription'])
  sample.select_one('.request-topline .pill').string=t('学习用品','Study')
  sample.select_one('h3').string=t(*COPY['buyTitle']);sample.select_one('.request-description').string=t(*COPY['buyDescription']);sample.select_one('.request-state').string=t(*COPY['wantedBuy'])
  sample.select_one('.request-budget strong').string='HK$ 100';sample.select_one('.request-facts').clear();sample.select_one('.request-facts').string='CityUHK campus'
  seek.select_one('.wanted-list').insert(0,sample);save(seek,'seeking')
  # These static routes render demo state safely in the browser; no API endpoint.
  for rel,kind in [('items/sale-example','sale-example'),('items/demo','item-preview'),('wanted/buy-example','buy-example'),('wanted/demo','wanted-preview'),('orders/demo','order'),('messages/demo','conversation')]:
   s=read('messages/9' if kind=='conversation' else 'items/2');s.body['data-demo-route']=rel+'/';s.body['data-route']='/'+rel+'/';s.body['data-market-screen']=kind
   s.body['class']=['preview-app','polished','market-demo','view-chat' if kind=='conversation' else 'view-market']
   sidebar=deepcopy(s.select_one('.conversation-sidebar')) if kind=='conversation' else None
   for key in list(s.body.attrs):
    if key.startswith('data-item-') or key in ('data-conversation','data-peer','data-blocked'):del s.body[key]
   for script in s.select('script[src="/showcase.js"]'):script.decompose()
   s.main.clear()
   if sidebar:
    wrapper=frag('<div class="app-container"><section class="message-shell"><div class="message-pane" data-market-screen-content></div></section></div>')
    wrapper.select_one('.message-shell').insert(0,sidebar);s.main.append(wrapper)
   else:s.main.append(frag('<div class="app-container"><div data-market-screen-content></div></div>'))
   s.title.string=t('示例流程 · Box Box Share','Demo flow · Box Box Share')
   save(s,rel)
