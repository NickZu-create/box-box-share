"""Opt-in group chat examples over the existing static Buddy and Messages pages."""
import json
from copy import deepcopy
from bs4 import BeautifulSoup as B

COPY={
 'actions':('群聊选项','Group options'),'messageActions':('消息选项','Message options'),'historyShort':('仅显示本次入群后的消息','Messages since this join only'),
 'sent':('示例消息已保存在本标签页','Sample message saved in this tab'),'sampleReply':('已添加合成示例回复','Synthetic sample reply added'),
 'storageError':('无法保存演示数据，请保留输入并检查浏览器存储设置。','Cannot save demo data. Keep your input and check browser storage settings.'),
 'invalidReport':('请填写至少 5 个非空白字符说明原因。','Please enter at least 5 non-whitespace characters describing the issue.'),
 'sendShort':('发送','Send'),'refreshShort':('手动刷新','Refresh manually'),'latest':('回到最新消息','Back to latest messages'),'emptyTitle':('从一句问候开始','Start with a hello'),
 'group':('Buddy 群聊','Buddy group chat'),'create':('一键建立群聊','Create group chat'),'join':('一键加入群聊','Join group chat'),'open':('进入群聊','Open group chat'),
 'rule':('获批成员自愿加入；只看本次入群后的消息。私聊继续保留。','Accepted members choose to join. Only messages since this join are shown. Private chats stay available.'),
 'pending':('申请获发起人接受后，才可以加入群聊。','Your application must be accepted before you can join the group.'),
 'history':('仅显示本次入群后的消息。群消息不会解锁私人联系方式。','Only messages since this join are visible. Group messages never unlock private contact details.'),
 'messages':('返回消息','Back to Messages'),'post':('查看招募','View recruitment'),'send':('发送群聊消息','Send group message'),'placeholder':('输入群聊消息…','Write to the group…'),
 'refresh':('刷新查看当前示例消息','Refresh sample messages'),'empty':('还没有本次入群后的消息，打个招呼吧。','No messages since this join. Say hello.'),
 'leave':('退出群聊','Leave group chat'),'leaveTitle':('确认退出群聊？','Leave this group chat?'),'leaveNote':('不会退出 Buddy。重新加入只看再次入群后的消息。','You stay in the Buddy team. Rejoining starts a new history window.'),
 'cancel':('取消','Cancel'),'confirm':('确认','Confirm'),'close':('关闭','Close'),'members':('群聊成员','Group members'),'host':('发起人','Host'),
 'tools':('演示工具（不联系任何人）','Demo tools (nobody is contacted)'),'peerJoin':('模拟 Jamie 自愿加入','Simulate Jamie choosing to join'),'peerJoined':('Jamie 已加入示例群聊','Jamie joined the sample group'),
 'reply':('模拟 Jamie 回复','Simulate Jamie reply'),'replyBody':('大家好，我们在校园公共地点集合。（合成示例）','Hello everyone. Let’s meet in a public campus location. (Synthetic example)'),
 'noAccess':('先在招募页自愿加入，才可以查看群聊。','Choose to join from the recruitment page before viewing this group.'),
 'report':('举报消息','Report message'),'reportTitle':('举报这条群聊消息','Report this group message'),'reason':('原因（5–2000 字）','Reason (5–2000 characters)'),
 'reportSaved':('示例举报已记录在当前标签页，没有发送给任何人。','Sample report recorded in this tab; nothing was sent.'),'invalid':('请输入 1–2000 字的消息。','Enter a message of 1–2000 characters.'),
 'login':('演示登录后继续','Sign in to the demo to continue'),'groupNote':('仅当前标签页合成演示，不是实时群聊，不会发送给真实成员。','Synthetic demo in this tab only. No realtime transport or messages to real members.'),
}

def finalize_groups(out,tr,version):
 for lang in ('hans','zh','en'):
  t=lambda z,e:tr(lang,z,e)
  def load(rel):return B((out/lang/rel/'index.html').read_text(encoding='utf-8'),'html.parser')
  titles={str(i):load(f'buddy/{i}').select_one('main h1').get_text(' ',strip=True).split(' / ')[0 if lang=='en' else -1] for i in (1,2)}
  for ident in ('1','2'):
   s=load('messages/9');s.body['class']=['preview-app','polished','market-demo','view-chat','view-group-demo']
   for k in list(s.body.attrs):
    if k.startswith('data-item') or k in ('data-market-screen','data-conversation','data-peer','data-blocked'):del s.body[k]
   s.body['data-demo-route']=f'messages/groups/{ident}/';s.body['data-route']=f'/messages/groups/{ident}/';s.body['data-group-demo']=ident
   for script in s.select('script[src="/showcase.js"]'):script.decompose()
   for row in s.select('.thread-row.current'):row['class']=[x for x in row['class'] if x!='current'];row.attrs.pop('aria-current',None)
   pane=s.select_one('.message-pane');pane.clear();pane['data-group-demo-host']=''
   s.title.string=t('Buddy 群聊 · Box Box Share','Buddy group chat · Box Box Share')
   dest=out/lang/'messages/groups'/ident/'index.html';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(str(s),encoding='utf-8')
  for p in (out/lang).rglob('index.html'):
   s=B(p.read_text(encoding='utf-8'),'html.parser')
   if not s.main:continue
   rel='/'.join(p.relative_to(out/lang).parts[:-1])
   if rel in ('buddy/1','buddy/2','buddy/3'):
    ident=rel.split('/')[-1];heading=s.select_one('main h1')
    if heading:heading.insert_after(B('<div class="group-demo-controls" data-buddy-group-control="'+ident+'"></div>','html.parser'))
   strings={k:t(*v) for k,v in COPY.items()};strings['titles']=titles
   s.body.append(B('<script type="application/json" id="group-copy">'+json.dumps(strings,ensure_ascii=False).replace('<','\\u003c')+'</script>','html.parser'))
   s.head.append(B(f'<link rel="stylesheet" href="/group-demo.css?v={version}"><script defer src="/group-demo.js?v={version}"></script>','html.parser'))
   p.write_text(str(s),encoding='utf-8')
