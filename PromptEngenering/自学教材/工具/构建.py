#!/usr/bin/env python3
"""从唯一教材源和现有题目生成 LaTeX 与离线网页；不改动原题文件。"""
from pathlib import Path
import re, json, subprocess, hashlib, html
ROOT=Path(__file__).resolve().parents[3]
BASE=Path(__file__).resolve().parents[1]
SRC=BASE/'源文件'
BUILD=BASE/'构建'
APP=BASE/'练习台'
CONFIG=json.loads((SRC/'课程配置.json').read_text())
BUILD.mkdir(exist_ok=True)
APP.mkdir(exist_ok=True)

def pandoc(text, fmt):
    args=['pandoc','-f','markdown-smart+tex_math_dollars+raw_tex','-t',fmt,'--wrap=none']
    if fmt=='latex': args += ['--top-level-division=chapter','--no-highlight']
    if fmt=='html5': args += ['--mathml']
    return subprocess.run(args,input=text,text=True,capture_output=True,check=True).stdout

def extract():
    questions=[]
    sources=sorted((ROOT/'PromptEngenering/题目').glob('*.md'))+[ROOT/'PromptJudge/题目/历史题目_01.md']
    for path in sources:
        raw=path.read_text()
        # 每个二级标题为一个正式条目；复习记录的三级标题不另计。
        headings=list(re.finditer(r'^## (.+)$',raw,re.M))
        for n,m in enumerate(headings):
            start=m.end(); end=headings[n+1].start() if n+1<len(headings) else len(raw)
            before=raw[:m.start()]
            anchors=re.findall(r'<a id="([^"]+)"',before)
            anchor=anchors[-1]
            body=raw[start:end]
            full_body=body
            body=re.split(r'### 历史复习记录',body)[0]
            body=re.sub(r'<a id="[^"]+"></a>','',body)
            body=re.sub(r'<!--.*?-->','',body,flags=re.S).strip()
            stem=re.search(r'^题目：\s*\n((?:>.*\n?)+)',body,re.M)
            opts=re.findall(r'^- ([A-Z])\. (.*)$',body,re.M)
            if not stem or len(opts)<2: raise ValueError(f'无法识别题目 {path} {anchor}')
            answer_match=re.search(r'官方答案[^\n]*：\s*\n(?:正确答案：)?\s*([A-Z]+)',body)
            official=bool(answer_match)
            if not answer_match: answer_match=re.search(r'正确选项：\s*([A-Z]+)',body)
            if not answer_match: raise ValueError(f'缺答案 {anchor}')
            answer=list(answer_match.group(1))
            key=anchor.removeprefix('s-')
            if path.parts[-3]=='PromptJudge': key='judge-'+key
            matching=[c for c in CONFIG['chapters'] if key in c['questions']]
            if len(matching)!=1: raise ValueError(f'章节映射异常 {key}')
            chapter=matching[0]
            original_stem='\n'.join(re.sub(r'^> ?', '',line) for line in stem.group(1).strip().splitlines())
            original_options=[{'key':k,'text':v} for k,v in opts]
            if len(set(k for k,v in opts))!=len(opts): raise ValueError(f'重复选项 {key}')
            if any(a not in [o['key'] for o in original_options] for a in answer): raise ValueError(key)
            # 原记录全文作为答案后的来源面板，保留已存解析，数学围栏仅作显示转换。
            display=re.sub(r'\\\[\s*([\s\S]*?)\s*\\\]',lambda m:'\n$$\n'+m.group(1)+'\n$$\n',re.sub(r'<a id="[^"]+"></a>|<!--.*?-->','',full_body,flags=re.S).strip())
            display=re.sub(r'(?m)^((?![-*>] ).+)\n(?=[->] )',r'\1\n\n',display)
            questions.append(dict(id=key,title=m.group(1),stem=original_stem,options=original_options,answer=answer,multiple=len(answer)>1,official=official,chapter=chapter['id'],source=str(path.relative_to(ROOT)),anchor=anchor,record=pandoc(display,'html5'),note=CONFIG['clarifications'].get(key,''),source_hash=hashlib.sha256(raw.encode()).hexdigest()))
    expected=[k for c in CONFIG['chapters'] for k in c['questions']]
    assert set(expected)=={q['id'] for q in questions}
    assert len(expected)==len(questions)==len(set(expected))
    return questions

questions=extract()
text=(SRC/'教材.md').read_text()
parts=re.split(r'^# (.+)$',text,flags=re.M)
chapters=[]; latex=[]
for i in range(1,len(parts),2):
    title,body=parts[i],parts[i+1]
    c=CONFIG['chapters'][len(chapters)].copy()
    c['title']=title
    c['html']=pandoc(body,'html5')
    c['refs']=re.findall(r'\[R(\d+)\]',body)
    c['html']=re.sub(r'(<h3[^>]*>参考(?:与解释|设计与自查标准)</h3>)(.*?)(?=<h3|$)',lambda m:'<details><summary>展开参考与解释（先独立作答）</summary>'+m.group(2)+'</details>',c['html'],flags=re.S)
    c['count']=sum(q['chapter']==c['id'] for q in questions)
    chapters.append(c)
    tex=pandoc('# '+title+'\n'+body,'latex')
    cueiter=iter(c['cues'])
    tex=re.sub(r'(\\section\{[^\n]+\}\s*\\label\{[^}]+\})',lambda m:m.group(1)+'\n\\cue{'+next(cueiter)+'}',tex)
    tex=re.sub(r'\\label\{([^}]+)\}',lambda m:'\\label{c'+str(c['id'])+'-'+m.group(1)+'}',tex)
    latex.append(tex)
(BUILD/'body.tex').write_text('\n'.join(latex))
pre=pandoc((SRC/'前言.md').read_text(),'latex').replace('\\chapter{怎样学这本书}','\\chapter*{怎样学这本书}\\addcontentsline{toc}{chapter}{怎样学这本书}')
(BUILD/'preface.tex').write_text(pre)

def esc(s):
    return s.replace('\\','\\textbackslash{}').replace('&',r'\&').replace('%',r'\%').replace('_',r'\_').replace('#',r'\#')

appendix=['\\chapter{题目与教材对照}', '本表给出全部独立题目的主归属章。编号 01-001 表示历史题目第 01 分册的锚点 s-01-001；judge 表示 PromptJudge 专题。历史别名 s-04-009 与 s-04-010 指向同一道邮件风格题，重复复习记录不另计。没有把其他专题所有含 Prompt 一词的题扩成新题库。', f'练习台共 {len(questions)} 题，其中提示词工程 {len(questions)-1} 题，提示词评测 1 题。正文覆盖与题目映射用于检索，不代表原题或历史解析已得到独立官方核验。']
for c in chapters:
    appendix+=['\\section{'+esc(c['short'])+'}', '\\begin{longtable}{@{}p{0.17\\linewidth}p{0.77\\linewidth}@{}}\\toprule 编号 & 题目定位 \\\\ \\midrule\\endhead']
    for q in questions:
        if q['chapter']==c['id']:
            title=re.sub(r'^\d{4}-\d{2}-\d{2}\s*','',q['title'])
            appendix+=[esc(q['id'])+' & '+esc(title)+r' \\']
    appendix+=['\\bottomrule\\end{longtable}']
appendix+=['\\chapter{研究与文档导航}', '按正文引用编号查阅。研究摘要与官方文档用于核验定义及适用边界；书中未把特定实验数值宣传为普遍性能保证。以下链接核对于 2026 年 11 月 1 日。']
for rid,title,url,note in CONFIG['references']:
    appendix+=['\\begin{minipage}{\\linewidth}\\small\\noindent{\\small\\sffamily\\bfseries\\color{teal}['+rid+'] '+esc(title)+'}\\par',esc(note)+'\\par{\\footnotesize\\url{'+url+'}}\\par\\end{minipage}\\par\\medskip']
appendix+=['\\chapter{复习用的概念连接}', '\\section{五组最值得区分的边界}', '任务指令说明做什么；上下文提供背景；输入是本轮对象；输出格式约定交付形式。少样本提示改当前输入；微调改可训练参数；软提示训练额外向量；检索提供可更新的事实。', '温度调概率分布，top-p 截候选集合，最大输出限制管容量，明确长度要求管表达。稳定性、正确性与复现性分别检验。', 'CoT 组织步骤；Self-Consistency 聚合多个最终答案；ToT 搜索分支；CoVe 对初稿提出问题并独立验证；PoT 用程序表达并执行计算；ReAct 在行动与观察之间调整计划。', 'JSON 语法、Schema 结构、业务事实和操作权限分层检查。来源存在不等于来源支持，语义接近不等于逻辑蕴含，模型自信不等于已被校准。', '容量截断、证据利用不足与对话漂移要分别诊断。开发集用于修改，独立测试用于检查泛化，回归集检查旧能力，线上观察检查现实变化。', '\\section{回忆时不要只背缩写}', '合上书，任选一种技术，按四句话复述：它解决的困难；它的关键步骤；与最相似技术的区别；不能保证的事情。举一个你自己的例子，再回练习台选择对应章节。没有把握的正确答案也进入复习，直到可以解释原因。']
(BUILD/'appendix.tex').write_text('\n\n'.join(appendix))
(BUILD/'main.tex').write_text((SRC/'版式.tex').read_text())
# 持久化的是可重新生成的交付网页；不另外维护原题 JSON 副本。
payload=dict(version=1,chapters=chapters,questions=questions,references=CONFIG['references'])
data=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
page=(SRC/'练习台.html').read_text().replace('/*__DATA__*/',data)
(APP/'index.html').write_text(page)
print(json.dumps(dict(questions=len(questions),official=sum(q['official'] for q in questions),chapters=len(chapters),body_characters=len(text),source_files=5),ensure_ascii=False))
