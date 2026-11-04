"""Final, scoped refinement layer for the existing synthetic demo.

Moves existing profile controls intact, preserving names, labels, validation,
help IDs and market-demo hooks. It does not create fields or new workflows.
"""
from bs4 import BeautifulSoup as B


def _fragment(markup):
    return B(markup, 'html.parser')


def _profile(s, t):
    form = s.select_one('[data-market-profile]')
    page = s.select_one('main .page')
    if not form or not page or 'experience-profile-form' in form.get('class', []):
        return
    page['class'] = page.get('class', []) + ['experience-profile-page']
    form['class'] = [c for c in form.get('class', []) if c != 'panel'] + ['experience-profile-form']
    account = page.select_one('.panel')
    if account and account is not form:
        account['class'] = account.get('class', []) + ['experience-account-summary']

    sections = []
    definitions = [
        ('identity', ('显示在社区里的你', 'Your community profile'),
         ('昵称和头像帮助大家认出你。', 'Your nickname and photo help people recognize you.'), ['nickname', 'avatar']),
        ('buddy', ('介绍一下自己', 'A little about you'),
         ('兴趣、技能和交流语言，方便找到合适的校园搭子。', 'Share interests, skills and languages for campus activities.'),
         ['bio', 'interests', 'skills', 'languages']),
    ]
    for key, title, description, names in definitions:
        section = _fragment('<section class="experience-profile-section" aria-labelledby="profile-' + key + '-title">'
                            '<div class="experience-section-heading"><h2 id="profile-' + key + '-title">' + t(*title) +
                            '</h2><p>' + t(*description) + '</p></div><div class="profile-field-grid"></div></section>').section
        grid = section.select_one('.profile-field-grid')
        for name in names:
            control = form.select_one('[name="' + name + '"]')
            row = control.find_parent('p') if control else None
            if row and row.parent is form:
                row['class'] = row.get('class', []) + ['experience-profile-field']
                if name == 'bio':
                    row['class'].append('profile-field-wide')
                grid.append(row.extract())
        sections.append(section)

    # Keep the existing explanatory paragraph with the introduction fields.
    for hint in list(form.find_all('p', class_='hint', recursive=False)):
        hint['class'] = hint.get('class', []) + ['experience-form-note']
        sections[1].append(hint.extract())

    for fieldset in list(form.find_all('fieldset', recursive=False)):
        fieldset['class'] = fieldset.get('class', []) + ['experience-profile-section']
        grid = _fragment('<div class="profile-field-grid"></div>').div
        for label in list(fieldset.find_all('label', recursive=False)):
            grid.append(label.extract())
        # The legend and privacy note stay before the controls; the rule stays after them.
        rule = fieldset.find(class_='contact-rule', recursive=False)
        if rule:
            rule.insert_before(grid)
        else:
            fieldset.append(grid)
        sections.append(fieldset.extract())

    footer = _fragment('<div class="experience-save-bar"></div>').div
    actions = form.select_one('.actions')
    if actions:
        footer.append(actions.extract())
    status = form.select_one('.market-profile-status')
    if status:
        status['aria-live'] = 'polite'
        footer.append(status.extract())
    for section in sections:
        form.append(section)
    form.append(footer)


def finalize_experience(out, tr, version):
    """Call last, after marketplace, student and group demo generation."""
    for lang in ('hans', 'zh', 'en'):
        t = lambda z, e: tr(lang, z, e)
        for path in (out / lang).rglob('index.html'):
            s = B(path.read_text(encoding='utf-8'), 'html.parser')
            if not s.head or not s.main:
                continue
            route = '/'.join(path.relative_to(out / lang).parts[:-1])
            s.body['class'] = s.body.get('class', []) + ['experience-refined']
            if route == 'profile':
                _profile(s, t)
            for previous in s.select('link[href^="/experience.css"],script[src^="/experience.js"]'):
                previous.decompose()
            s.head.append(_fragment(f'<link rel="stylesheet" href="/experience.css?v={version}">'
                                    f'<script defer src="/experience.js?v={version}"></script>'))
            path.write_text(str(s), encoding='utf-8')
