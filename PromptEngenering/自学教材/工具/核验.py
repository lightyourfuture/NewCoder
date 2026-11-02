#!/usr/bin/env python3
"""独立对照交付网页与原题；不以生成器的成功退出代替完整性检查。"""
from pathlib import Path
from html.parser import HTMLParser
import hashlib,json,re,subprocess
BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[1]
class Text(HTMLParser):
    def __init__(self): super().__init__();self.parts=[]
    def handle_data(self,data): self.parts.append(data)
def norm(s):return re.sub(r'\s+','',s)
page=(BASE/'练习台/index.html').read_text()
data=json.loads(re.search(r'const DATA=(.*?);\nconst KEY=',page,re.S)[1])
assert len(data['questions'])==102
assert sum(q['official'] for q in data['questions'])==4
assert len(data['chapters'])==11
source_counts={}
for q in data['questions']:
    raw=(ROOT/q['source']).read_text()
    assert hashlib.sha256(raw.encode()).hexdigest()==q['source_hash']
    # 按保存标题独立定位，不复用构建器的锚点切分逻辑。
    entry=raw.split('## '+q['title']+'\n',1)[1].split('\n## ',1)[0]
    primary=entry.split('### 历史复习记录')[0]
    lines=primary.splitlines()
    stem=[];in_stem=False
    opts=[]
    for line in lines:
        if line=='题目：': in_stem=True;continue
        if in_stem:
            if line.startswith('>'):stem.append(line.removeprefix('>').removeprefix(' '));continue
            if stem:in_stem=False
        if re.match(r'^- [A-Z]\. ',line):opts.append({'key':line[2], 'text':line[5:]})
    assert '\n'.join(stem)==q['stem'],q['id']+' 题干'
    assert opts==q['options'],q['id']+' 选项'
    parser=Text();parser.feed(q['record']);rendered=''.join(parser.parts)
    if q['official']:
        official=re.search(r'^官方解析[^\n]*：\s*\n(.*?)(?=\n(?:核对|补充|通俗|易错|知识点|参考))',primary,re.M|re.S)
        assert official,q['id']+' 解析定位'
        assert norm(official[1]) in norm(rendered),q['id']+' 官方解析完整性'
    if '历史复习记录' in entry:
        assert '2026-06-16' in rendered,q['id']+' 历史复习未保留'
    source_counts[q['source']]=source_counts.get(q['source'],0)+1
assert sorted(source_counts.values())==[1,11,30,30,30]
# 无远程字体、脚本或图片依赖；参考链接不影响离线使用。
assert not re.search(r'<(?:script|link|img)[^>]+(?:src|href)=["\']https?://',page,re.I)
# 公式既有网页 MathML，也保留在教材源中；编译日志不得有缺字或溢出。
assert any('<math' in c['html'] for c in data['chapters'])
log=(BASE/'构建/main.log').read_text()
assert not re.search(r'Overfull|Missing character:|LaTeX Error|multiply defined',log)
pdf=BASE/'构建/main.pdf'
assert pdf.exists()
text=subprocess.run(['pdftotext',str(pdf),'-'],check=True,text=True,capture_output=True).stdout
for c in data['chapters']: assert norm(c['title']) in norm(text),c['title']
print('通过：102 道原题题干与全部选项、4 份官方解析、历史复习、11 章、公式、离线依赖与 LaTeX 日志。')
