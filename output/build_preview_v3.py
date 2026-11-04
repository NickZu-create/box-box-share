"""Isolated synthetic preview. Reads static export only; never opens a product DB."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
from html import escape as E
from bs4 import BeautifulSoup as B
from opencc import OpenCC
import re,shutil,time
from polish_preview import polish
from marketplace_demo import decorate,finalize
from student_preview import finalize_student
from group_preview import finalize_groups
from experience_preview import finalize_experience
ROOT=Path(__file__).resolve().parent.parent
SRC=ROOT/'output/showcase-baseline' if (ROOT/'output/showcase-baseline').exists() else ROOT/'public-demo/dist';OUT=ROOT/'output/design-preview'
HK=timezone(timedelta(hours=8));NOW=datetime.now(HK);CC=OpenCC('s2t')
def txt(n):return n.get_text(' ',strip=True) if n else ''
def read(p):return B(p.read_text(encoding='utf8'),'html.parser')
def frag(v):return B(v,'html.parser')
def tr(l,z,e):return e if l=='en' else CC.convert(z) if l=='zh' else z
def ico(n):return f'<img class="ui-icon" src="/preview-assets/icons/{n}.svg" alt="" width="20" height="20">'
def title(v,l):return v.split(' / ')[0] if l=='en' else v.split(' / ')[-1]
def art(l):return '<div class="brand-art" aria-hidden="true">'+str(read(SRC/l/'index.html').select_one('.hero-art svg'))+'</div>'
def select(l,name,opts,cls):return f'<label class="{cls}"><span class="sr-only">{E(opts[0][1])}</span><select name="{name}" aria-label="{E(opts[0][1])}">'+''.join(f'<option value="{E(v)}">{E(t)}</option>' for v,t in opts)+'</select></label>'
def empty(l):return '<div class="empty-results" id="empty-results" hidden><h2>'+tr(l,'没有找到符合条件的内容','No matches this time')+'</h2><p>'+tr(l,'试试更短的关键词或减少筛选条件。','Try a shorter keyword or remove a filter.')+'</p><button class="button secondary" type="button" data-clear-filters>'+tr(l,'清除筛选','Clear filters')+'</button></div>'
def common(s,l):
 h=s.select_one('header');h['class']=['site-header'];nav=h.select_one('nav');nav['class']=['desktop-nav'];links={a['href']:a for a in nav.select('a')}
 old=s.select_one('.mobile-nav')
 if old:old.decompose()
 mobile='<nav class="mobile-primary" aria-label="'+tr(l,'主要导航','Primary navigation')+'">';used=set()
 for route,icon in [('', 'package'),('seeking/','search'),('buddy/','users'),('messages/','message-circle')]:
  href=f'/{l}/{route}';a=links.get(href);sel=' selected' if a and 'selected' in a.get('class',[]) else ''
  mobile+=f'<a class="mobile-destination{sel}" href="{href}"'+(' aria-current="page"' if sel else '')+'>'+ico(icon)+'<span>'+E(txt(a))+'</span></a>';used.add(href)
 mobile+='<details class="more-nav"><summary>'+ico('ellipsis')+'<span>'+tr(l,'更多','More')+'</span></summary><div class="more-panel">'
 for href,a in links.items():
  if href not in used:mobile+=f'<a href="{href}">{E(txt(a))}</a>';used.add(href)
 for route,label in [('items/new/',tr(l,'发布物品','List an item')),('profile/',tr(l,'个人资料','Profile'))]:mobile+=f'<a href="/{l}/{route}">{label}</a>'
 s.body.append(frag(mobile+'</div></details></nav>'))
 publish=h.select_one('a.button')
 if publish:publish.clear();publish.append(frag(ico('plus')+'<span class="publish-label">'+tr(l,'发布物品','List an item')+'</span>'))
 if publish and 'view-seeking' in s.body.get('class',[]):
  publish['href']=f'/{l}/wanted/new/';publish['aria-label']=tr(l,'发布求借','Post a request');publish.select_one('.publish-label').string=tr(l,'发布求借','Post a request')
 footer=s.select_one('footer')
 if footer:footer['class']=['site-footer']
 notice=s.new_tag('div',attrs={'class':'demo-strip'});notice.string=tr(l,'本地设计预览 · 示例数据 · 操作不会发送或保存','Local design preview · Sample data · Actions do not send or save');h.insert_after(notice)
 for b in s.select('.showcase-banner'):b.decompose()
def explore(l):
 t=lambda z,e:tr(l,z,e);source=read(SRC/l/'index.html');cards=source.select('.item-card');cats=[(o.get('value',''),txt(o)) for o in source.select('select[name=category] option')];catmap={label:v for v,label in cats}
 html='<div class="app-container"><section class="explore-intro"><div><span class="eyebrow">'+t('一物一程，皆是相逢。','GOOD THINGS GO AROUND')+'</span><h1>'+t('校园好物，借来刚好。','Good things. Shared on campus.')+'</h1><p>'+t('发现、借用与分享，让身边的好物继续发光。','Find something useful. Lend something loved.')+'</p></div>'+art(l)+'</section><div class="explore-toolbar"><div class="view-tabs"><a class="active" href="/'+l+'/">'+t('借用物品','Borrow items')+'</a><a href="/'+l+'/seeking/">'+t('寻物广场','Seeking')+'</a></div><span class="result-total">'+t('校园交接 · 按日期申请','Campus meet-ups · Request your dates')+'</span></div>'
 html+='<form class="filter-form" data-filter="items" novalidate><label class="filter-query">'+ico('search')+'<span class="sr-only">'+t('搜索物品','Search items')+'</span><input name="q" placeholder="'+t('搜索相机、计算器、台灯…','Search cameras, calculators, lamps…')+'"></label>'+select(l,'category',cats,'filter-category')
 html+='<label class="filter-price"><span class="sr-only">'+t('最高日租（HKD）','Max daily price (HKD)')+'</span><input name="price" type="number" min="0" step="0.01" aria-label="'+t('最高日租（HKD）','Max daily price (HKD)')+'" placeholder="'+t('日租上限','Max HK$')+'"></label><details class="filter-dates"><summary>'+ico('calendar-days')+t('借用日期','Dates')+ico('chevron-down')+'</summary><div class="date-fields"><label>'+t('开始','From')+'<input type="datetime-local" name="start"></label><label>'+t('结束','Until')+'<input type="datetime-local" name="end"></label><p class="filter-help">'+t('香港时间。仅筛选示例可借窗口，实际借用仍须检查订单占用。','Hong Kong time. Filters sample windows only; reservations still need checking.')+'</p></div></details><button class="button filter-submit">'+ico('search')+t('搜索','Search')+'</button></form><p class="filter-feedback" id="filter-status" role="status" aria-live="polite"></p><div class="collection-heading"><h2>'+t('探索好物','Explore the collection')+'</h2><p class="hint" id="result-count"></p></div><div class="item-grid">'
 for c in cards:
  href=c.a['href'];d=read(SRC/(href.strip('/')+'/index.html'));name=txt(c.h3);label=txt(c.select_one('.image-tag'));category=catmap.get(label,'other');price=txt(c.select_one('.price'));num=re.search(r'\d+(?:\.\d+)?',price);amount=float(num[0]) if num else 0
  windows=[datetime.strptime(v,'%Y-%m-%d %H:%M').replace(tzinfo=HK) for v in re.findall(r'\d{4}-\d\d-\d\d \d\d:\d\d',txt(d.select_one('main')))[:2]]
  facts={txt(dt):txt(dt.find_next_sibling('dd')) for dt in d.select('.facts dt')};maxdays=next((int(re.search(r'\d+',v)[0]) for k,v in facts.items() if re.search('最長|最长|Maximum',k) and re.search(r'\d+',v)),14)
  own=c.select_one('.card-bottom');avatar=txt(own.select_one('.avatar'));owner=' '.join(str(n).strip() for n in own.contents if isinstance(n,str)).strip();location=txt(c.select_one('.meta')).lstrip('⌖ ')
  attrs=f'data-category="{category}" data-price="{amount}" data-max-days="{maxdays}" data-search="{E(txt(d.select_one("main")),quote=True)}"'
  if len(windows)==2:attrs+=f' data-start="{windows[0].isoformat()}" data-end="{windows[1].isoformat()}"'
  full=' → '.join(f'{v:%Y-%m-%d %H:%M}' for v in windows);short=' – '.join(v.strftime('%m/%d') if windows[0].year==windows[-1].year else v.strftime('%Y/%m/%d') for v in windows)
  state=t('可借窗口已结束','Window ended') if windows and windows[-1]<NOW else t('已上架','Listed');money=t('免费借用','Free to borrow') if amount==0 else f'HK$ {amount:g}<small> / '+t('日','day')+'</small>'
  icon={'tech':'camera','study':'calculator','home':'lamp-desk','outdoor':'tent','creative':'mic'}.get(category,'package')
  photo=c.select_one('.item-image img');image_class='has-photo' if photo else 'no-photo'
  media=f'<img class="item-photo" src="{E(photo["src"],quote=True)}" alt="{E(title(name,l),quote=True)}" loading="lazy">' if photo else ico(icon)+'<span>'+t('暂无照片','No photo')+'</span>'
  html+=f'<article class="item-tile {image_class}" {attrs}><a class="tile-link" href="{href}"><div class="tile-media {image_class}">'+media+'</div><div class="tile-content"><span class="tile-category">'+E(label)+'</span><h3 class="tile-title" title="'+E(name,quote=True)+'">'+E(title(name,l))+'</h3><div class="tile-price">'+money+'</div><p class="tile-meta">'+ico('map-pin')+E(location)+'</p><p class="tile-dates" title="'+E(full)+'">'+ico('calendar-days')+E(short)+'</p><div class="tile-footer"><span class="avatar tiny">'+E(avatar)+'</span><span>'+E(owner)+'</span><span class="status">'+state+'</span></div></div></a></article>'
 result=frag(html+'</div>'+empty(l)+'<p class="collection-note">'+t('已上架不等于所选时段一定可借；借用仍须确认时段和物主审批。','Listed does not guarantee availability. Your dates and lender approval still need confirmation.')+'</p></div>')
 count=result.select_one('#result-count').extract()
 result.select_one('.result-total').replace_with(count)
 result.select_one('.collection-heading').decompose()
 result.select_one('.item-grid').insert_before(frag('<h2 class="sr-only">'+t('探索好物','Explore items')+'</h2>'))
 return str(result)

def seeking(l):
 t=lambda z,e:tr(l,z,e);source=read(SRC/l/'seeking/index.html');cards=source.select('.wanted-card');cats=[(o.get('value',''),txt(o)) for o in source.select('select[name=category] option')]
 html='<div class="app-container"><section class="explore-intro seeking-intro"><div><span class="eyebrow">'+t('SEEKING · 让需要遇见分享','SEEKING / SOMEONE NEARBY CAN HELP')+'</span><h1>'+t('<span class="intro-phrase">你需要的，</span><span class="intro-phrase">或许就在隔壁。</span>','What you need might be next door.')+'</h1><p>'+t('说说你想借什么，让闲置与需要在校园里相遇。','Tell the community what you would like to borrow.')+'</p></div>'+art(l)+'</section><div class="explore-toolbar"><div class="view-tabs"><a href="/'+l+'/">'+t('借用物品','Borrow items')+'</a><a class="active" href="/'+l+'/seeking/">'+t('寻物广场','Seeking')+'</a></div><div class="collection-summary"><p class="hint" id="result-count"></p><button class="filter-reset" type="button" data-clear-filters hidden>'+ico('repeat')+t('清除筛选','Clear filters')+'</button><a class="request-publish" href="/'+l+'/wanted/new/">'+ico('plus')+t('发布求借','Post a request')+'</a></div></div>'
 html+='<form class="filter-form" data-filter="wanted" novalidate><label class="filter-query">'+ico('search')+'<span class="sr-only">'+t('搜索求借需求','Search requests')+'</span><input name="q" placeholder="'+t('搜索大家想借的物品…','Search what people are looking for…')+'"></label>'+select(l,'category',cats,'filter-category')+'<label class="filter-price"><span class="sr-only">'+t('总预算上限（HKD）','Max total budget (HKD)')+'</span><input name="price" type="number" min="0" step="0.01" placeholder="'+t('总预算上限','Max budget')+'" aria-label="'+t('总预算上限（HKD）','Max total budget (HKD)')+'"></label><details class="filter-dates"><summary>'+ico('calendar-days')+t('需要日期','Dates needed')+ico('chevron-down')+'</summary><div class="date-fields"><label>'+t('开始','From')+'<input type="datetime-local" name="start"></label><label>'+t('结束','Until')+'<input type="datetime-local" name="end"></label><p class="filter-help">'+t('香港时间；显示与你选择的时段有重叠的需求。','Hong Kong time. Shows requests overlapping your selected period.')+'</p></div></details><button class="button filter-submit">'+ico('search')+t('搜索','Search')+'</button></form><p class="filter-feedback" id="filter-status" role="status" aria-live="polite"></p><h2 class="sr-only">'+t('社区求借需求','Community borrowing requests')+'</h2><div class="wanted-list">'
 for c in cards:
  href=c['href'];detail=read(SRC/(href.strip('/')+'/index.html'));dates=[datetime.strptime(v,'%Y-%m-%d %H:%M').replace(tzinfo=HK) for v in re.findall(r'\d{4}-\d\d-\d\d \d\d:\d\d',txt(detail.select_one('main')))[:2]];name=txt(c.h3);description=txt(c.select_one('p:not(.meta)'));amount=float(c.get('data-price','0'));category=c.get('data-category','other');label=txt(c.select_one('.pill'));ownerbox=c.select_one('.card-bottom');avatar=txt(ownerbox.select_one('.avatar'));owner=' '.join(str(n).strip() for n in ownerbox.contents if isinstance(n,str)).strip();metas=c.select('p.meta');location=txt(metas[1]).lstrip('⌖ ') if len(metas)>1 else '';expired=len(dates)==2 and dates[1]<=NOW
  state=t('已过期','Expired') if expired else t('正在寻找','Seeking');full=' → '.join(f'{v:%Y-%m-%d %H:%M}' for v in dates);short=' – '.join(f'{v:%m/%d %H:%M}' for v in dates)
  attrs=f'data-category="{category}" data-price="{amount}" data-search="{E(name+" "+description,quote=True)}"'
  if len(dates)==2:attrs+=f' data-start="{dates[0].isoformat()}" data-end="{dates[1].isoformat()}"'
  html+=f'<a class="wanted-tile" href="{href}" {attrs}><div class="request-content"><div class="request-topline"><span class="pill">'+E(label)+'</span><span class="request-state'+(' expired' if expired else '')+'">'+state+'</span></div><h3>'+E(title(name,l))+'</h3><p class="request-description">'+E(description)+'</p><div class="request-facts"><p title="'+E(full)+'">'+ico('calendar-days')+E(short)+'</p><p>'+ico('map-pin')+E(location)+'</p></div><div class="request-owner"><span class="avatar tiny">'+E(avatar)+'</span>'+E(owner)+'</div></div><div class="request-budget"><div class="budget-amount"><span>'+t('总预算','Total budget')+'</span><strong>HK$ '+f'{amount:g}'+'</strong></div><span class="request-cta">'+t('查看需求','View request')+ico('arrow-up-right')+'</span></div></a>'
 html+='</div>'+empty(l)+'<div class="seeking-guidance"><div>'+ico('message-circle')+'<p>'+t('有合适的物品？打开需求，用你已上架的物品回应。','Have something suitable? Open a request and offer one of your listed items.')+'</p></div><a href="/'+l+'/lost-found/">'+t('遗失或捡到物品？去失物招领','Lost or found something? Visit Lost & Found')+ico('chevron-right')+'</a></div></div>'
 return html

def prepare_collection(s,l):
 s.body['class'].append('collection-page')
 s.select_one('#result-count')['aria-live']='polite'
 for cls,name in [('filter-category',tr(l,'物品分类','Category')),('filter-price',None)]:
  node=s.select_one('.'+cls+' > .sr-only')
  if node:
   node['class']=['filter-label']
   if name:node.string=name
 if 'view-explore' in s.body['class']:
  count=s.select_one('#result-count');summary=s.new_tag('div',attrs={'class':'collection-summary'});count.replace_with(summary);summary.append(count)
  summary.append(frag('<button class="filter-reset" type="button" data-clear-filters hidden>'+ico('repeat')+tr(l,'清除筛选','Clear filters')+'</button>'))
  original=read(SRC/l/'index.html').select_one('.hero')
  original['class']=['hero','borrow-hero','hero-motion']
  original['id']='collection-hero'
  slot=s.new_tag('div',attrs={'class':'borrow-hero-slot'})
  s.select_one('.explore-intro').replace_with(slot);slot.append(original)
 else:
  hero=s.select_one('.explore-intro');hero['class'].append('hero-motion');hero['id']='collection-hero'
 toolbar=s.select_one('.explore-toolbar');toolbar['id']='discover'
 container=s.select_one('main .app-container')
 content=s.new_tag('div',attrs={'class':'collection-content'})
 hero=container.select_one('.borrow-hero-slot') or container.select_one('.explore-intro')
 for node in list(hero.next_siblings):content.append(node.extract())
 container.append(content)

def buddy(l,route):
 t=lambda z,e:tr(l,z,e);s=read(SRC/l/route/'index.html')
 html='<div class="app-container"><section class="buddy-intro"><div><span class="eyebrow">BUDDY / CAMPUS TOGETHER</span><h1>'+t('一个人去，不如一起去。','Better with good company.')+'</h1><p>'+t('一起学习、运动，或把一个好点子做出来。','Study, play, or bring a good idea to life.')+'</p></div>'+art(l)+'<a class="button" href="/'+l+'/buddy/new/">'+ico('plus')+t('发布招募','Create a post')+'</a></section><div class="buddy-tabs view-tabs">'+''.join(str(a) for a in s.select('.section-head .tabs a'))+'</div><form class="filter-form buddy-filters" data-filter="buddy" novalidate><label class="filter-query">'+ico('search')+'<span class="sr-only">'+t('搜索招募','Search posts')+'</span><input name="q" placeholder="'+t('搜索活动、地点或技能…','Search activities, places or skills…')+'"></label>'
 for name,cls in [('kind','filter-kind'),('when','filter-when'),('state','filter-state')]:
  opts=[(o.get('value',''),txt(o)) for o in s.select(f'select[name={name}] option')]
  if name=='state':opts=[('open',t('可申请的招募','Open to applications')),('all',t('全部状态','All states')),('full',t('已满','Full')),('closed',t('已关闭','Closed')),('ended',t('已结束','Ended'))]
  html+=select(l,name,opts,cls)
 html+='<button class="button filter-submit">'+t('搜索','Search')+'</button></form><p class="filter-feedback" id="filter-status" role="status" aria-live="polite"></p><div class="collection-heading"><h2>'+t('找到一起出发的人','Find your people')+'</h2><p class="hint" id="result-count"></p></div><div class="recruitment-list">'
 for c in s.select('.buddy-card'):
  start=datetime.fromisoformat(c['data-start']).astimezone(HK);metas=c.select('p.meta');time_label=txt(metas[0]).lstrip('▦ ');match=re.search(r'→\s*(\d\d)/(\d\d)\s*(\d\d):(\d\d)',time_label);end=datetime(start.year,*map(int,match.groups()),tzinfo=HK) if match else start
  if end<start:end=end.replace(year=start.year+1)
  count=re.search(r'(\d+)\s*/\s*(\d+)',txt(c.select_one('.buddy-count')));remaining=int(count[2])-int(count[1]);state=c.get('data-state','open')
  if end<NOW:state='ended'
  elif state=='open' and remaining<=0:state='full'
  states={'open':t('招募中','Open'),'full':t('已满','Full'),'closed':t('已关闭','Closed'),'ended':t('已结束','Ended')};name=txt(c.h3);description=txt(c.select_one('p:not(.meta)'));owner=txt(c.select_one('.card-bottom')).replace('✓','').strip()
  html+=f'<a class="recruitment-row" href="{c["href"]}" data-kind="{c.get("data-kind","")}" data-category="{c.get("data-category","")}" data-state="{state}" data-start="{start.isoformat()}" data-end="{end.isoformat()}" data-search="{E(txt(c),quote=True)}"><div class="recruitment-main">'+str(c.select_one('.pill-row'))+'<h2>'+E(title(name,l))+'</h2><p>'+E(description)+'</p><span class="recruitment-owner">'+ico('users')+E(owner)+'</span></div><div class="recruitment-facts">'
  for cls,icon,value in [('time','calendar-days',time_label),('place','map-pin',txt(metas[1]).lstrip('⌖ ')),('languages','globe',txt(metas[2]).lstrip('◌ '))]:html+=f'<p class="{cls}">'+ico(icon)+E(value)+'</p>'
  html+='</div><div class="recruitment-action"><span class="status">'+states[state]+'</span><strong class="spots">'+t(f'剩余 {max(0,remaining)} 个名额',f'{max(0,remaining)} spots left')+'</strong><span class="row-cta">'+t('查看招募','View post')+ico('arrow-up-right')+'</span></div></a>'
 return html+'</div>'+empty(l)+'<p class="collection-note">'+t('名额不含发起人。申请须经发起人审批，接受后可在消息中联系。','Spots exclude the host. Applications need host approval; accepted members can message each other.')+'</p></div>'

def threads(l):
 inbox=read(SRC/l/'messages/index.html');seen=set();rows=[]
 for a in inbox.select_one('.panel').select('a.list-row'):
  href=a.get('href','')
  if href in seen or not re.search(r'/messages/\d+/$',href):continue
  seen.add(href);chat=read(SRC/(href.strip('/')+'/index.html'));parties=txt(a.p).split(' ↔ ');other=next((p for p in parties if 'Demo · You' not in p),parties[0]);pill=txt(a.select_one('.pill'));topic=txt(a.h3).removeprefix(pill).strip();bubbles=chat.select('.bubble');last=bubbles[-1] if bubbles else None
  if topic==other and (pill in ('好友',) or pill.lower() in ('friend','friends')):topic=''
  rows.append(dict(href=href,name=other,topic=topic,type=pill,preview=txt(last.p) if last else tr(l,'尚未开始对话','No messages yet'),stamp=txt(last.small).split(' · ')[-1] if last else '',id=int(href.rstrip('/').split('/')[-1])))
 return sorted(rows,key=lambda r:(r['stamp'],r['id']),reverse=True)
def sidebar(l,current):
 t=lambda z,e:tr(l,z,e);html='<aside class="conversation-sidebar"><h1>'+t('消息','Messages')+'</h1><p class="sidebar-note">'+t('借用、Buddy 与校园里的小事','Shared things, plans and conversations')+'</p><div class="thread-list">'
 for d in threads(l):
  selected=' current' if d['href']==current else ''
  html+=f'<a class="thread-row{selected}" href="{d["href"]}"'+(' aria-current="page"' if selected else '')+'><span class="avatar">'+E(d['name'][0])+'</span><span class="thread-summary"><strong>'+E(d['name'])+'</strong><span class="thread-topic"><span class="pill">'+E(d['type'])+'</span>'+E(d['topic'])+'</span><span class="thread-preview">'+E(d['preview'])+'</span><time>'+E(d['stamp'])+'</time></span></a>'
 if not threads(l):html+='<div class="chat-empty"><h2>'+t('还没有对话','No conversations yet')+'</h2><a class="button" href="/'+l+'/">'+t('浏览物品','Explore items')+'</a></div>'
 return html+'</div><a class="sidebar-tools" href="/'+l+'/messages/#inbox-tools">'+ico('shield-check')+t('通知、好友与安全管理','Notifications, friends & safety')+ico('chevron-right')+'</a></aside>'
def messages(l,route):
 t=lambda z,e:tr(l,z,e);current=f'/{l}/{route}';original=read(SRC/l/route/'index.html');html='<div class="app-container"><section class="message-shell">'+sidebar(l,current)+'<div class="message-pane">'
 if route=='messages/':html+='<div class="chat-empty"><span class="eyebrow">BOX BOX SHARE / MESSAGES</span><h2>'+t('好好沟通，让分享更简单。','A little conversation goes a long way.')+'</h2><p>'+t('选择一个对话，继续聊聊物品、活动或失物招领。','Choose a conversation about an item, an activity or Lost & Found.')+'</p><p class="hint">'+t('消息需要手动刷新。','Refresh manually to see new messages.')+'</p><a class="button secondary" href="/'+l+'/">'+t('浏览校园好物','Explore items')+'</a></div>'
 else:
  d=next(d for d in threads(l) if d['href']==current);section=original.select_one('main section');context=section.select_one('p.hint');html+='<div class="chat-header"><a class="breadcrumb" href="/'+l+'/messages/">'+ico('arrow-left')+t('返回消息','All conversations')+'</a><div class="chat-heading"><div><h2>'+E(d['name'])+'</h2><p class="thread-topic"><span class="pill">'+E(d['type'])+'</span>'+E(d['topic'])+'</p></div></div><div class="chat-context">'+(''.join(str(a) for a in context.select('a')) if context else '')+'</div><div class="chat-actions"><details class="more-menu"><summary>'+ico('ellipsis')+'<span>'+t('更多操作','More actions')+'</span></summary><div class="menu-content">'
  tools=section.select_one('.conversation-tools')
  if tools:html+=''.join(str(child) for child in tools.contents)
  html+='</div></details></div></div><div class="chat-body">'+str(section.select_one('.messages-list'))+'</div>';composer=section.select_one('form.chat-form')
  if composer:
   composer['class']=['chat-composer'];button=composer.select_one('button');button.clear();button.append(frag(ico('send')+'<span>'+t('发送','Send')+'</span>'));html+=str(composer)
  else:
   notice=section.select_one('.panel>.notice')
   if notice:html+=str(notice)
  html+='<div class="refresh-row"><span>'+t('手动更新消息','Messages update on refresh')+'</span><a href="'+current+'">'+ico('repeat')+t('刷新','Refresh')+'</a></div>'
 html+='</div></section>'
 if route=='messages/':html+='<details class="inbox-management" id="inbox-tools"><summary>'+ico('shield-check')+t('通知、好友与安全管理','Notifications, friends & safety')+'</summary>'+''.join(str(panel) for panel in original.select('.panel')[1:])+'</details>'
 return html+'</div>'

if __name__=='__main__':
 shutil.copytree(SRC,OUT,dirs_exist_ok=True);version=str(int(time.time()))
 for source_path in SRC.rglob('*.html'):
  rel=source_path.relative_to(SRC);path=OUT/rel;lang=rel.parts[0]
  if lang not in ('en','zh','hans'):continue
  route='/'.join(rel.parts[1:-1]);route=route+'/' if route else '';s=read(SRC/rel)
  if not s.head or not s.main:continue
  key=route in ('','seeking/','buddy/','buddy/activities/','buddy/teams/','messages/') or bool(re.fullmatch(r'messages/\d+/',route))
  view='explore' if not route else 'seeking' if route=='seeking/' else 'buddy' if route.startswith('buddy') else 'inbox' if route=='messages/' else 'chat'
  if key:
   s.body['class']=['preview-app','view-'+view]
   for link in s.select('link[rel=stylesheet]'):link.decompose()
   for script in s.select('script[src="/showcase.js"]'):script.decompose()
   s.main.clear();s.main.append(frag(explore(lang) if view=='explore' else seeking(lang) if view=='seeking' else buddy(lang,route) if view=='buddy' else messages(lang,route)))
   if view in ('explore','seeking'):prepare_collection(s,lang)
  else:
   s.body['class']=s.body.get('class',[])+['legacy-page']
   if re.fullmatch(r'items/\d+/',route):
    s.body['class'].append('detail-preview')
    grid=s.select_one('.detail-grid')
    if grid:
     columns=grid.find_all('div',recursive=False)
     if len(columns)==2:columns[0]['class']=columns[0].get('class',[])+['item-story'];columns[1]['class']=columns[1].get('class',[])+['item-decision']
     price=grid.select_one('.price')
     if price:
      windows=re.findall(r'\d{4}-\d\d-\d\d \d\d:\d\d',txt(grid))[:2]
      copy=tr(lang,'计费以此处日租和申请时的费用预览为准，描述不会更改租金。','Charges use this daily price and the request quotation. Description text does not change the rate.')
      info='<p class="pricing-basis">'+copy+'</p>'
      if windows:info='<p class="decision-window">'+ico('calendar-days')+tr(lang,'可借窗口：','Availability window: ')+E(' → '.join(windows))+'</p>'+info
      price.insert_after(frag(info))
  common(s,lang);polish(s,lang,route,tr,ico);decorate(s,lang,route,tr,ico);s.head.append(frag(f'<link rel="stylesheet" href="/preview.css?v={version}"><script defer src="/preview.js?v={version}"></script>'));path.write_text(str(s),encoding='utf8')
  if view in ('explore','seeking') and key:
   s.head.append(frag(f'<link rel="stylesheet" href="/collection.css?v={version}"><link rel="stylesheet" href="/hero-motion.css?v={version}"><script defer src="/collection-motion.js?v={version}"></script>'));path.write_text(str(s),encoding='utf8')
  s.head.append(frag(f'<link rel="stylesheet" href="/polish.css?v={version}"><script defer src="/polish.js?v={version}"></script>'));path.write_text(str(s),encoding='utf8')
  s.head.append(frag(f'<link rel="stylesheet" href="/market-demo.css?v={version}"><script defer src="/demo-core.js?v={version}"></script><script defer src="/market-demo.js?v={version}"></script>'));path.write_text(str(s),encoding='utf8')
 finalize(OUT,tr,ico,version)
 finalize_student(OUT,tr,version)
 finalize_groups(OUT,tr,version)
 finalize_experience(OUT,tr,version)
 print(OUT)
