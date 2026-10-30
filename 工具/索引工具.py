#!/usr/bin/env python3
"""检查题目正文、索引与候选；只读，不修改或合并题目。"""
from pathlib import Path
import argparse,re,unicodedata,difflib,sys,os
ROOT=Path(__file__).resolve().parent.parent

def norm(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC',s)).lower()

def entries():
    records=[]
    for file in sorted(ROOT.glob('*/题目/*.md')):
        text=file.read_text(encoding='utf-8')
        blocks=list(re.finditer(r'^## (.+)\n([\s\S]*?)(?=^## |\Z)',text,re.M))
        for m in blocks:
            stem=re.search(r'^题目[：:]\s*\n([\s\S]*?)\n选项[：:]',m[2],re.M)
            if not stem:continue
            anchor_matches=list(re.finditer(r'<a id="([^"]+)"></a>',text[:m.start()]))
            if not anchor_matches:raise ValueError(f'{file}: 无题目锚点 {m[1]}')
            anchor=anchor_matches[-1][1]
            txt=re.sub(r'^>\s*','',stem[1],flags=re.M).strip().replace('\n',' ')
            records.append(dict(topic=file.parts[-3],path=file.relative_to(ROOT).as_posix(),title=m[1],stem=txt,anchor=anchor))
    return records

def links(index):
    text=index.read_text(encoding='utf-8')
    return [(m[1],m[2]) for m in re.finditer(r'^- \[(.*?)\]\(([^)]+)\)',text,re.M)]

def check():
    records=entries();errors=[]
    files=[ROOT/'题目总索引.md',*sorted(ROOT.glob('*/题目索引.md'))]
    cache={}
    lookup={}
    contents={}
    for index in files:
        cache[index]=links(index)
        lookup[index]=set()
        for title,link in cache[index]:
            path,_,anchor=link.partition('#');target=(index.parent/path).resolve()
            if not target.is_file():errors.append(f'{index.relative_to(ROOT)}: 目标不存在 {link}');continue
            lookup[index].add((target,anchor))
            if anchor and f'<a id="{anchor}"></a>' not in contents.setdefault(target,target.read_text(encoding='utf-8')):
                errors.append(f'{index.relative_to(ROOT)}: 锚点不存在 {link}')
    for r in records:
        file=ROOT/r['path'];topic=ROOT/r['topic']/'题目索引.md'
        for idx in [files[0],topic]:
            if idx not in cache:errors.append(f'专题索引不存在 {idx}');continue
            if (file.resolve(),r['anchor']) not in lookup[idx]:errors.append(f'{idx.relative_to(ROOT)}: 未收录 {r["path"]}#{r["anchor"]} {r["title"]}')
    if errors:
        print('\n'.join(errors));print(f'错误 {len(errors)} 条');return 1
    print(f'通过：{len(records)} 个题目条目，{len(files)} 个索引，目标、锚点和正文覆盖均已检查。')
    print('说明：历史重复条目/复习别名可能指向同一题；语义正确性、原题完整性与用户作答仍需人工对照。')
    return 0

def rebuild(output_dir, write):
    records=entries(); count=0
    groups={r['topic'] for r in records}|{x.parent.name for x in ROOT.glob('*/题目索引.md')}
    for index in [ROOT/'题目总索引.md',*[ROOT/t/'题目索引.md' for t in sorted(groups)]]:
        topic=None if index.parent==ROOT else index.parent.name
        chosen=[r for r in records if topic is None or r['topic']==topic]
        canonical={(r['title'],(ROOT/r['path']).resolve(),r['anchor']) for r in chosen}
        lines=['# '+('全项目题目总索引' if topic is None else topic+' 题目索引')+'\n\n',
               '自动生成的检索入口：请打开正文逐项比较题干和全部选项；复习别名保留在末尾。\n\n']
        for r in chosen:
            rel=os.path.relpath(ROOT/r['path'],index.parent)
            lines.append(f'- [{r["title"]}]({rel}#{r["anchor"]})｜{r["stem"]}\n')
        # Carry existing batch/merged historical aliases; do not reconstruct or invent lost records.
        aliases=[]
        if index.exists():
            for line in index.read_text(encoding='utf-8').splitlines():
                m=re.match(r'^- \[(.*?)\]\(([^)]+)\)｜',line)
                if m:
                    path,_,anchor=m[2].partition('#');target=(index.parent/path).resolve()
                    if (m[1],target,anchor) in canonical:continue
                    if not target.is_file() or (anchor and f'<a id="{anchor}"></a>' not in target.read_text(encoding='utf-8')):
                        raise ValueError(f'不能保留失效别名：{index} {line}')
                    aliases.append(line)
        if aliases:lines.append('\n## 历史批次与复习别名\n\n');lines.extend(line+'\n' for line in aliases)
        text=''.join(lines);dest=(output_dir/index.relative_to(ROOT)) if output_dir else index
        if output_dir or write:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(text,encoding='utf-8')
        print(f'{index.relative_to(ROOT)}: 正文 {len(chosen)}，保留别名 {len(aliases)}')
        count+=1
    print(f'{count} 个索引'+('已写入。' if write else '已写入预览目录。' if output_dir else '预览完成，未写入。'))
    print('重要：复习别名依赖现存索引；若索引和批次记录同时丢失，不能凭空重建。')

def search(query,limit):
    q=norm(query);scored=[]
    for r in entries():
        v=norm(r['stem']);grams={q[i:i+2] for i in range(max(0,len(q)-1))};coverage=sum(g in v for g in grams)/max(1,len(grams));score=1.0 if q in v else max(difflib.SequenceMatcher(None,q,v).ratio(),coverage*0.8)
        if score>=0.28:scored.append((score,r))
    for score,r in sorted(scored,key=lambda x:-x[0])[:limit]:
        print(f'{score:.3f} {r["path"]}#{r["anchor"]} | {r["title"]}\n  {r["stem"]}')
    print('提示：匹配仅用于找候选，不自动判断重复；请逐项比较完整题干、所有选项与字母。')

parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True);sub.add_parser('check');p=sub.add_parser('search');p.add_argument('query');p.add_argument('--limit',type=int,default=10);p=sub.add_parser('rebuild');p.add_argument('--output-dir',type=Path);p.add_argument('--write',action='store_true');args=parser.parse_args()
try:
    if args.command=='check':sys.exit(check())
    if args.command=='rebuild':
        if args.output_dir and args.write:raise ValueError('不能同时指定 --output-dir 和 --write')
        rebuild(args.output_dir,args.write)
    else:search(args.query,args.limit)
except (OSError,ValueError) as e:
    print(f'检查失败：{e}',file=sys.stderr);sys.exit(2)
