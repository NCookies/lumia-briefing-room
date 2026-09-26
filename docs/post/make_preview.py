import re
src = open('arca-intro.html', encoding='utf-8').read()
imgs = ['01-clip-list.png', '04-first-run.png', '02-options-data.png', '03-options-cleanup.png']
empty = re.compile(r'(vertical-align:top;height:120px;">)(</td>)')
it = iter(imgs)
out = empty.sub(lambda m: m.group(1) + f'<img src="img/{next(it)}" style="width:100%;display:block;border:0;">' + m.group(2), src)
open('arca-intro.preview.html', 'w', encoding='utf-8').write(
    '<!doctype html><meta charset="utf-8"><title>미리보기</title><body style="margin:0;padding:16px;background:#ffffff;">'
    + out + '</body>')
