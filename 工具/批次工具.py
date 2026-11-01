#!/usr/bin/env python3
"""批量定位候选、检查平台复制文本和逐题核验；只读，不归档或合并。"""
from pathlib import Path
import argparse
import difflib
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parent.parent
HEADER = re.compile(r'(?m)^(单选题|多选题)[ \t]*\n(?:(?!\d+\.)[^\n]+\n)?(\d+)\.[ \t]*\n')
OPTION = re.compile(r'(?m)^([A-D])\s*$')

def compact(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', s))

def clean(s):
    return re.sub(r'\s+', '', s)

def parse(path):
    text = path.read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    heads = list(HEADER.finditer(text))
    if not heads:
        raise ValueError('未识别到题目头；请检查平台格式，不能据此视为无题。')
    labels = list(re.finditer(r'(?m)^(?:单选题|多选题)\s*$', text))
    if len(labels) != len(heads):
        raise ValueError(f'找到 {len(labels)} 个题型标记但只识别 {len(heads)} 题；请人工检查未识别部分。')
    result = []
    for i, head in enumerate(heads):
        body = text[head.end():heads[i+1].start() if i+1 < len(heads) else len(text)]
        matches = list(OPTION.finditer(body))
        if [m.group(1) for m in matches[:4]] != list('ABCD'):
            raise ValueError(f'第 {head.group(2)} 题选项无法可靠识别；请人工检查原文。')
        matches = matches[:4]
        answer = re.search(r'(?m)^正确答案[：:]\s*([A-D、,， ]+)', body)
        explanation = re.search(r'(?m)^官方解析[：:]\s*\n', body)
        if bool(answer) != bool(explanation):
            raise ValueError(f'第 {head.group(2)} 题答案或解析缺失；请人工检查原文。')
        end = answer.start() if answer else len(body)
        opts = [body[m.end():matches[j+1].start() if j < 3 else end].strip() for j,m in enumerate(matches)]
        if not answer:
            # End-of-page UI cannot safely be distinguished from option text.
            opts[3] = re.split(r'(?m)^(?:答题卡|继续练习|夜间|顶部)\s*$',opts[3])[0].strip()
        official = None
        if explanation:
            tail = body[explanation.end():]
            stop = re.search(r'(?m)^知识点[：:]|^题友讨论\(', tail)
            if not stop:
                raise ValueError(f'第 {head.group(2)} 题官方解析结束位置不明确；请人工检查。')
            official = tail[:stop.start()].strip()
            if not official: raise ValueError(f'第 {head.group(2)} 题官方解析为空。')
        result.append({'number': int(head.group(2)), 'type': head.group(1),
                       'stem': body[:matches[0].start()].strip(), 'options': opts,
                       'answer': re.sub(r'[^A-D]', '', answer.group(1)) if answer else None,
                       'official': official})
    if len({x['number'] for x in result}) != len(result):
        raise ValueError('题号重复，不能安全匹配；请人工检查。')
    return result

def records():
    result = []
    for file in sorted(ROOT.glob('*/题目/*.md')):
        text = file.read_text(encoding='utf-8')
        sections = list(re.finditer(r'(?m)^## (.+)$', text))
        for i, section in enumerate(sections):
            body = text[section.end():sections[i+1].start() if i+1 < len(sections) else len(text)]
            stem = re.search(r'(?ms)^题目[：:]\s*\n(.*?)\n\s*选项[：:]', body)
            if not stem: continue
            anchors = list(re.finditer(r'<a id="([^"]+)"></a>', text[:section.start()]))
            if not anchors: continue
            options = re.findall(r'(?m)^-\s*([A-D])[.、]\s*(.*)$', body)
            if [x[0] for x in options[:4]] != list('ABCD'): continue
            value = re.sub(r'(?m)^>\s*', '', stem.group(1)).strip()
            result.append({'path': file.relative_to(ROOT).as_posix(), 'anchor': anchors[-1].group(1),
                           'title': section.group(1), 'stem': value,
                           'options': [x[1] for x in options[:4]]})
    return result

def show(path, anchor):
    file = (ROOT/path).resolve()
    if not file.is_relative_to(ROOT) or not file.is_file(): raise ValueError('路径不在项目内或文件不存在。')
    text = file.read_text(encoding='utf-8')
    marker = f'<a id="{anchor}"></a>'
    if marker not in text: raise ValueError('找不到锚点。')
    start = text.index(marker)
    # Adjacent anchors can be aliases for the same entry.
    tail = text[start+len(marker):]
    adjacent = re.match(r'(?:\s*<a id="[^"]+"></a>)*', tail)
    offset = len(marker)+adjacent.end()
    end = re.search(r'(?m)^<a id="[^"]+"></a>', text[start+offset:])
    print(text[start:start+offset+end.start()] if end else text[start:])

def candidates(qs, limit):
    known = records()
    for q in qs:
        exact, similar = [], []
        for r in known:
            same_stem = compact(q['stem']) == compact(r['stem'])
            same_opts = all(compact(a) == compact(b) for a,b in zip(q['options'],r['options']))
            if same_stem and same_opts:
                exact.append(r)
            else:
                ratio = difflib.SequenceMatcher(None, compact(q['stem']), compact(r['stem'])).ratio()
                if same_stem or ratio >= .57: similar.append((ratio,r))
        print(f"题{q['number']}：完全一致候选 {len(exact)}，相近候选 {len(similar)}")
        for r in exact:
            print(f"  完全一致候选 {r['path']}#{r['anchor']} | {r['title']}")
        for score,r in sorted(similar,key=lambda x:-x[0])[:limit]:
            print(f"  相近 {score:.2f} {r['path']}#{r['anchor']} | {r['title']}")
    print('候选仅作定位；必须打开原记录核对完整题干、选项、来源和锚点，不能自动合并。')

def verify(qs, index, batch, math_format):
    if any(q['official'] is None for q in qs):
        raise ValueError('包含无官方解析的题，不能执行官方归档完整性验证。')
    index_text = index.read_text(encoding='utf-8')
    sections = list(re.finditer(r'(?m)^## (.+)$', index_text))
    matching = [i for i, m in enumerate(sections) if m.group(1).strip() == batch]
    if len(matching) != 1:
        raise ValueError(f'索引批次标题匹配到 {len(matching)} 个；请提供唯一的完整标题。')
    i=matching[0]
    index_text=index_text[sections[i].end():sections[i+1].start() if i+1<len(sections) else None]
    errors = []
    for q in qs:
        n=q['number']
        matches = re.findall(rf'(?m)^- \[[^\]]*题{n}(?:（[^\]]*）|\s+[^\]]*)?\]\(([^)]+)\)', index_text)
        if len(matches)!=1:
            errors.append(f'题{n}: 批次索引匹配到 {len(matches)} 条，需人工检查'); continue
        path,sep,anchor=matches[0].partition('#')
        f=(index.parent/path).resolve()
        if not f.is_relative_to(ROOT) or not f.is_file() or not sep:
            errors.append(f'题{n}: 索引目标无效');continue
        text=f.read_text(encoding='utf-8');mark=f'<a id="{anchor}"></a>'
        if mark not in text: errors.append(f'题{n}: 锚点不存在');continue
        start=text.index(mark); section_end=re.search(r'(?m)^## ',text[start+len(mark):])
        if not section_end: errors.append(f'题{n}: 标题不存在');continue
        title_start=start+len(mark)+section_end.start()
        next_title=re.search(r'(?m)^## ',text[title_start+3:])
        section=text[title_start:title_start+3+next_title.start() if next_title else None]
        # Only the specific review block is accepted for duplicated questions.
        review=re.search(rf'(?m)^### .*本次复习：第 {n} 题\s*$',section)
        current=section[review.start():] if review else section
        stem=re.search(r'(?ms)^题目[：:]\s*\n(.*?)\n\s*选项[：:]',section)
        actual_stem=re.sub(r'(?m)^>\s*','',stem.group(1)).strip() if stem else ''
        if clean(q['stem'])!=clean(actual_stem): errors.append(f'题{n}: 题干不匹配或缺失')
        options=re.findall(r'(?m)^-\s*([A-D])[.、]\s*(.*)$',section)
        for j, (letter,expected) in enumerate(zip('ABCD',q['options'])):
            if len(options)<=j or options[j][0]!=letter or clean(options[j][1])!=clean(expected):
                errors.append(f'题{n}: 选项{letter}不匹配或缺失')
        if not re.search(rf'(?m)^题型[：:]\s*{re.escape(q["type"])}\s*$',current): errors.append(f'题{n}: 题型不匹配或缺失')
        if not re.search(rf'(?m)^题号[：:]\s*{n}\s*$',current): errors.append(f'题{n}: 题号不匹配或缺失')
        if not re.search(rf'(?m)^官方答案[：:]\s*\n\s*{re.escape(q["answer"])}\s*$',current): errors.append(f'题{n}: 答案不匹配或缺失')
        official=re.search(r'(?ms)^官方解析[：:]\s*\n(.*?)(?=^用户作答[：:]|^核对|^补充|^通俗|^知识点总结|^### |\Z)',current)
        e,a=clean(q['official']),clean(official.group(1)) if official else ''
        if math_format: e,a=e.replace('$',''),a.replace('$','')
        if e!=a: errors.append(f'题{n}: 官方解析不匹配或缺失')
    if errors:
        print('\n'.join(errors));print(f'未通过：{len(errors)} 项异常。');return 1
    print(f'通过：{len(qs)} 题题型、题号、题干、选项、官方答案和解析均有对应内容。')
    print('说明：按字段比较文本，不验证语义、事实与官方结论正确性；需结合人工核对。')
    if math_format: print('提示：启用数学格式宽松比较，美元符号差异须人工复核。')
    return 0

def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='cmd',required=True)
    for name in ('inspect','duplicates'):
        s=sub.add_parser(name);s.add_argument('source',type=Path)
        if name=='duplicates': s.add_argument('--limit',type=int,default=2)
    s=sub.add_parser('show');s.add_argument('path');s.add_argument('anchor')
    s=sub.add_parser('verify');s.add_argument('source',type=Path);s.add_argument('batch_index',type=Path);s.add_argument('--batch',required=True);s.add_argument('--math-format',action='store_true')
    args=p.parse_args()
    if args.cmd=='show': show(args.path,args.anchor);return 0
    qs=parse(args.source)
    if args.cmd=='inspect':
        print(f"识别 {len(qs)} 题；官方答案及解析 {sum(q['official'] is not None for q in qs)} 题。")
        print('答案：'+' '.join(f"{q['number']}:{q['answer'] or '未提供'}" for q in qs))
        print('提示：成绩、用户作答与可能遗漏的页面内容须查看原文，不能推断。')
    elif args.cmd=='duplicates': candidates(qs,args.limit)
    else: return verify(qs,args.batch_index,args.batch,args.math_format)
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,OSError) as e:
        print(f'无法安全处理：{e}',file=sys.stderr);sys.exit(2)
