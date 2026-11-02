#!/usr/bin/env python3
"""在已编译、已核验后发布本地 PDF 和轻量离线包。"""
from pathlib import Path
import shutil,zipfile,subprocess,sys
BASE=Path(__file__).resolve().parents[1]
ROOT=BASE.parents[1]
subprocess.run([sys.executable,str(BASE/'工具/核验.py')],check=True)
OUT=ROOT/'output/pdf'
OUT.mkdir(parents=True,exist_ok=True)
NAME='提示词工程_从理解到独立应用.pdf'
shutil.copy2(BASE/'构建/main.pdf',OUT/NAME)
page=(BASE/'练习台/index.html').read_text().replace('../../../output/pdf/'+NAME,NAME)
start='''提示词工程自学包

1. 先阅读同目录的《提示词工程_从理解到独立应用.pdf》。
2. 用浏览器打开“开始学习.html”，可以离线读教材、练原题和自测。
3. 学习记录只在当前浏览器，换设备前导出 JSON，在新浏览器导入。
4. 若本地 HTML 被设备的文件预览器限制，请使用真正的浏览器或本地 HTTP 服务；PDF 可直接阅读。

102 道独立原题：提示词工程 101 道 + 提示注入 1 道。原题为现有仓库记录，来源区分已存官方答案与历史结论。教材为 Codex 编写，含 21 项原论文/官方文档导航。练习提示为静态资料，不调用模型 API。
'''
with zipfile.ZipFile(BASE/'提示词工程_离线自学包.zip','w',zipfile.ZIP_DEFLATED) as z:
    z.write(OUT/NAME,NAME)
    z.writestr('开始学习.html',page)
    z.writestr('先读我.txt',start)
print('已生成 PDF 与离线自学包。')
