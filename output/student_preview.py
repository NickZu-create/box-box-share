"""Small additions to the existing synthetic showcase, not production records."""
import json,re
from bs4 import BeautifulSoup as B

FIELDS=[('university','大学','University',120),('major','主修或课程','Major or Programme',160),('academic_year','年级','Academic year',40),('faculty','学院','Faculty or College',160)]
EXAMPLES={'1':('Demo','Electrical Engineering',''), '2':('Jamie','Electrical Engineering','MA1201 Calculus'), '3':('Alex','Computer Science','EE1001 Electronics')}

def finalize_student(out,tr,version):
 for lang in ('hans','zh','en'):
  t=lambda z,e:tr(lang,z,e)
  for p in (out/lang).rglob('index.html'):
   s=B(p.read_text(encoding='utf-8'),'html.parser');route='/'.join(p.relative_to(out/lang).parts[:-1])
   if not s.head or not s.main:continue
   if route=='profile':
    form=s.select_one('[data-market-profile]')
    fieldset=B('<fieldset class="profile-contacts student-fields"><legend>'+t('学生资料（全部选填）','Student profile (all optional)')+'</legend><p class="hint">'+t('自行填写，不代表学校认证。SSO 与课程表未连接；不会要求学校密码。','Self-reported, not university-certified. SSO and timetable access are not connected. No school password is requested.')+'</p></fieldset>','html.parser').fieldset
    for key,z,e,limit in FIELDS:
     fieldset.append(B(f'<label>{t(z,e)}<input name="{key}" maxlength="{limit}" autocomplete="off"></label>','html.parser'))
    form.select_one('.actions').insert_before(fieldset)
   if route in ('buddy','buddy/activities','buddy/teams'):
    form=s.select_one('[data-filter=buddy]');form.select_one('[name=q]')['placeholder']=t('搜索课程代码、名称、专业、活动…','Search course code, name, major, activity…')
    extra=B('<div class="student-refinements"><label>'+t('主修（选填）','Major (optional)')+'<input name="major" maxlength="160"></label><label>'+t('排序','Sort')+'<select name="sort"><option value="recommended">'+t('为你推荐','For you')+'</option><option value="time">'+t('按活动时间','Activity time')+'</option></select></label></div>','html.parser');form.append(extra)
    note=B('<p class="hint student-note">'+t('参考选填专业、近期搜索及已加入的示例活动。搜索不代表正式选课；尚未连接课表，时间冲突未知。示例成员专业和课程关联均为合成内容。','Uses optional major, recent searches and joined sample activities. Searches are not enrolment. Timetable access is not connected; class conflicts are unknown. Member majors and course associations are synthetic examples.')+'</p><div data-student-people></div>','html.parser');form.insert_after(note)
    for card in s.select('.recruitment-row'):
     ident=card['href'].rstrip('/').split('/')[-1];name,major,course=EXAMPLES.get(ident,('','',''))
     card['data-student-id']=ident;card['data-major']=major;card['data-person']=name
     card['data-search']=card.get('data-search','')+' '+major+' '+course
     if course:card.select_one('.recruitment-main').append(B('<p class="hint">'+t('示例关联：','Sample association: ')+course+'</p>','html.parser'))
   match=re.fullmatch(r'buddy/(\d+)',route)
   if match and match[1] in EXAMPLES:
    ident=match[1];_,major,course=EXAMPLES[ident];s.body['data-student-post']=ident
    h=s.select_one('main h1')
    if h:h.insert_after(B('<p class="hint">'+t('合成专业／课程示例：','Synthetic major/course example: ')+major+(' · '+course if course else '')+'</p>','html.parser'))
    s.main.append(B('<div class="app-container"><button type="button" class="text-button" data-student-dismiss>'+t('对此招募不感兴趣','Not interested in this post')+'</button><p role="status" data-student-feedback></p></div>','html.parser'))
   strings={key:t(z,e) for key,z,e in [('people','相关专业的示例成员','Sample members with related majors'),('restore','恢复此推荐','Restore this recommendation'),('dismiss','对此招募不感兴趣','Not interested in this post'),('saved','已降低此招募推荐优先级。','This post will be recommended less often.'),('restored','已恢复正常推荐。','Normal recommendation priority restored.'),('login','请先使用顶部的演示登录。','Use demo sign in above first.'),('sample','示例 · 专业由成员自行填写','Sample · self-reported major')]}
   s.body.append(B('<script type="application/json" id="student-copy">'+json.dumps(strings,ensure_ascii=False).replace('<','\\u003c')+'</script>','html.parser'))
   s.head.append(B(f'<link rel="stylesheet" href="/student-demo.css?v={version}"><script defer src="/student-demo.js?v={version}"></script>','html.parser'))
   p.write_text(str(s),encoding='utf-8')
