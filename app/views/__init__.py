"""页面视图层。

每个页面一个模块，只负责渲染与用户交互；业务逻辑仍在 app/ 下的
pipeline / interviewer / reporter 等模块里。

改造前三个页面全挤在 main.py（2156 行）里，`tab_resume_analysis` /
`tab_ai_interview` / `tab_report` 各自几百行，UI 逻辑与业务判断混写。
"""
