"""设计 token 与全局样式 —— 视图层唯一的样式来源。

为什么单独成文件：改造前这段样式有 480 行，混在 `main.py` 里，
而三个页面各自复制了一份页头 HTML（含一大坨内联 base64 logo）。
改一次配色要在四个地方同步，实际结果是它们早就不一致了。

★ 主题锁定亮色，理由见 `.streamlit/config.toml`：
  实测 Streamlit 既不跟随系统暗色，也不通过 CSS 变量暴露当前主题
  （`matchMedia('(prefers-color-scheme: dark)')` 为 true，但 `.stApp`
  的背景仍是 rgb(255,255,255)，且 `--background-color` 等全为空串）。
  用 `prefers-color-scheme` 写深色分支的结果是"深色卡片浮在白页上"。
"""
import streamlit as st

# ── 设计 token ────────────────────────────────────────────────
# 语义化命名。不要在组件里写死颜色，一律引用这里。
TOKENS = {
    # 品牌
    "brand":        "#009b91",
    "brand-600":    "#007f78",
    "brand-50":     "#edf9f7",
    "brand-100":    "#d8f1ee",
    # 语义色
    "success":      "#059669",
    "success-bg":   "#ecfdf5",
    "warning":      "#d97706",
    "warning-bg":   "#fffbeb",
    "danger":       "#dc2626",
    "danger-bg":    "#fef2f2",
    "info":         "#0284c7",
    "info-bg":      "#f0f9ff",
    # 中性
    "text":         "#173e58",
    "text-2":       "#607684",
    "text-3":       "#91a2ab",
    "surface":      "#ffffff",
    "surface-2":    "#f5f8f8",
    "surface-3":    "#edf3f3",
    "border":       "#dde8e9",
    "border-2":     "#cadbdc",
    # 形状
    "radius":       "14px",
    "radius-lg":    "20px",
    "shadow":       "0 4px 14px rgba(23,62,88,.055)",
    "shadow-md":    "0 10px 28px rgba(23,62,88,.075)",
}

# 面试题五个维度的配色，题卡与统计图共用一套
DIMENSION_COLORS = {
    "技术基础":   "#173e58",
    "项目深挖":   "#059669",
    "场景设计":   "#d97706",
    "行为面试":   "#0284c7",
    "模糊点追问": "#167f83",
}


def score_color(s) -> str:
    """分数 → 颜色。四档，与 score_tone 保持同一组阈值。"""
    try:
        s = float(s)
    except (TypeError, ValueError):
        return TOKENS["text-3"]
    if s >= 85:
        return TOKENS["success"]
    if s >= 70:
        return TOKENS["brand"]
    if s >= 55:
        return TOKENS["warning"]
    return TOKENS["danger"]


def score_tone(s) -> str:
    """分数 → 语义档位名（success / brand / warning / danger）。
    组件需要同时取前景色和背景色时用它，避免两处阈值写歪。"""
    try:
        s = float(s)
    except (TypeError, ValueError):
        return "neutral"
    if s >= 85:
        return "success"
    if s >= 70:
        return "brand"
    if s >= 55:
        return "warning"
    return "danger"


def _vars() -> str:
    return "\n".join(f"        --{k}: {v};" for k, v in TOKENS.items())


# ★ 不能用 % 或 str.format 做插值 —— CSS 里到处是 `width:100%` 和 `{`，
#   两种插值语法都会把它们当成占位符（实测报 "not enough arguments for
#   format string"）。用一个不可能出现在 CSS 里的哨兵串替换最省事。
_CSS_TEMPLATE = """
<style>
:root {
/*__TOKENS__*/
}

/* ── 基础排版 ───────────────────────────────────────── */
html, body, [class*="css"], .stApp {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif;
    color: var(--text);
}
.stApp { background: #f7f9f9; }

/* ★ padding-top 必须留出 Streamlit 自带顶栏的高度。
   实测：[data-testid="stHeader"] 高 60px、position:absolute、z-index 999990，
   而且【背景是不透明白色】。我一开始把 padding-top 压到 1.2rem(19.2px)，
   品牌条的 top 就落到 35px —— 正好钻到顶栏底下被盖住，
   而顶栏是 absolute 定位在滚动容器顶部的，所以**往上滑也露不出来**，
   表现为"那几行字只有一半"。60px + 呼吸空间 = 4.75rem。 */
.block-container { padding-top: .7rem; padding-bottom: 2rem; max-width: 1540px; }

/* 主页面只保留真实内容之间的间距。主题样式和0高滚动脚本不应制造空白。 */
.stMainBlockContainer > [data-testid="stVerticalBlock"] { gap: .6rem; }
.stMainBlockContainer > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"]:has(style),
.stMainBlockContainer > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"][height="0px"] {
    display: none !important;
}

/* 顶栏本身也对齐一下配色，否则白条压在浅灰页面上有一道明显的色差 */
[data-testid="stHeader"] { display:none!important; }
[data-testid="stSidebar"], [data-testid="collapsedControl"] { display:none!important; }

h1, h2, h3, h4 { color: var(--text); font-weight: 650; letter-spacing: -0.01em; }
p, li, span, label { color: var(--text-2); }
a { color: var(--brand); }

/* ── 页头 ──────────────────────────────────────────── */
.pg-head {
    display: flex; align-items: center; gap: 14px;
    padding: 20px 24px; margin: 18px 0 18px;
    background: #ffffff;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
}
.pg-head .pg-icon {
    width: 42px; height: 42px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    background: var(--brand); color: #fff;
    border-radius: 13px; font-size: 20px;
}
.pg-head .pg-title { font-size: 22px; font-weight: 760; color: var(--text); line-height: 1.25; }
.pg-head .pg-sub   { font-size: 13px; color: var(--text-2); margin-top: 3px; }

/* ── 区块标题 ───────────────────────────────────────── */
.sec-head {
    display: flex; align-items: baseline; gap: 10px;
    margin: 26px 0 12px;
}
.sec-head .sec-title {
    font-size: 15px; font-weight: 650; color: var(--text);
    position: relative; padding-left: 11px;
}
.sec-head .sec-title::before {
    content: ""; position: absolute; left: 0; top: 3px; bottom: 3px;
    width: 3px; border-radius: 2px; background: var(--brand);
}
.sec-head .sec-desc { font-size: 12px; color: var(--text-3); }

/* ── 结论横幅（结论先行）────────────────────────────── */
.verdict {
    display: flex; align-items: center; gap: 18px;
    padding: 18px 22px; border-radius: var(--radius-lg);
    border: 1px solid var(--border); background: var(--surface);
    box-shadow: var(--shadow); margin-bottom: 4px;
}
.verdict .v-bar { width: 4px; align-self: stretch; border-radius: 3px; }
.verdict .v-main { flex: 1; min-width: 0; }
.verdict .v-label { font-size: 12px; color: var(--text-3); letter-spacing: .04em; }
.verdict .v-text  { font-size: 19px; font-weight: 680; margin-top: 2px; }
.verdict .v-why   { font-size: 13px; color: var(--text-2); margin-top: 6px; line-height: 1.55; }
.verdict .v-score { text-align: center; flex-shrink: 0; padding-left: 18px; border-left: 1px solid var(--border); }
.verdict .v-num   { font-size: 34px; font-weight: 720; line-height: 1; }
.verdict .v-unit  { font-size: 13px; color: var(--text-3); }

/* ── 指标网格 ───────────────────────────────────────── */
.stat-grid { display: grid; gap: 16px; margin: 16px 0 6px; }
.stat-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 18px; padding: 18px 20px; box-shadow: var(--shadow);
}
.stat-card .sc-label { font-size: 12px; color: var(--text-3); margin-bottom: 5px; }
.stat-card .sc-value { font-size: 26px; font-weight: 760; color: var(--text); line-height: 1.15; }
.stat-card .sc-hint  { font-size: 11px; color: var(--text-3); margin-top: 4px; }

/* ── 评分条 ─────────────────────────────────────────── */
.bar-row { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.bar-row .br-label { width: 76px; flex-shrink: 0; font-size: 13px; color: var(--text-2); }
.bar-row .br-track { flex: 1; height: 7px; background: var(--surface-3); border-radius: 4px; overflow: hidden; }
.bar-row .br-fill  { height: 100%; border-radius: 4px; transition: width .45s ease; }
.bar-row .br-value { width: 42px; text-align: right; font-size: 13px; font-weight: 620; }

/* ── 题卡 ───────────────────────────────────────────── */
.q-card {
    background: var(--surface); border: 1px solid var(--border);
    border-left: 3px solid var(--brand);
    border-radius: var(--radius); padding: 13px 16px; margin-bottom: 9px;
    box-shadow: var(--shadow);
}
.q-card .q-text { font-size: 14px; color: var(--text); line-height: 1.55; font-weight: 520; }
.q-card .q-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; margin-top: 9px; }
.q-card .q-intent {
    font-size: 12px; color: var(--text-2); margin-top: 8px;
    padding-top: 8px; border-top: 1px dashed var(--border); line-height: 1.5;
}

/* ── 徽标 ───────────────────────────────────────────── */
.pill {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 9px; border-radius: 999px;
    font-size: 11px; font-weight: 600; line-height: 1.7;
    border: 1px solid transparent; white-space: nowrap;
}
.pill.success { color: var(--success); background: var(--success-bg); border-color: #a7f3d0; }
.pill.warning { color: var(--warning); background: var(--warning-bg); border-color: #fde68a; }
.pill.danger  { color: var(--danger);  background: var(--danger-bg);  border-color: #fecaca; }
.pill.brand   { color: var(--brand);   background: var(--brand-50);   border-color: #b9e4df; }
.pill.neutral { color: var(--text-2);  background: var(--surface-3);  border-color: var(--border); }

/* ── 证据列表 ───────────────────────────────────────── */
.ev-item {
    display: flex; gap: 9px; padding: 9px 12px; margin-bottom: 6px;
    border-radius: 8px; font-size: 13px; line-height: 1.55;
    border: 1px solid transparent;
}
.ev-item .ev-icon { flex-shrink: 0; }
.ev-item.success { background: var(--success-bg); border-color: #a7f3d0; color: #065f46; }
.ev-item.warning { background: var(--warning-bg); border-color: #fde68a; color: #92400e; }
.ev-item.danger  { background: var(--danger-bg);  border-color: #fecaca; color: #991b1b; }
.ev-item.neutral { background: var(--surface-2);  border-color: var(--border); color: var(--text-2); }

/* ── 空状态 ─────────────────────────────────────────── */
.empty {
    text-align: center; padding: 52px 26px;
    background: var(--surface); border: 1px dashed var(--border-2);
    border-radius: var(--radius-lg);
}
.empty .em-icon  { font-size: 40px; opacity: .5; }
.empty .em-title { font-size: 15px; font-weight: 620; color: var(--text); margin-top: 12px; }
.empty .em-desc  { font-size: 13px; color: var(--text-2); margin-top: 6px; line-height: 1.6; }

/* ── 步骤条 ─────────────────────────────────────────── */
.steps { display: flex; align-items: center; gap: 0; margin: 4px 0 18px; }
.steps .stp { display: flex; align-items: center; gap: 7px; font-size: 12px; color: var(--text-3); }
.steps .stp .dot {
    width: 20px; height: 20px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700;
    background: var(--surface-3); color: var(--text-3);
    border: 1px solid var(--border);
}
.steps .stp.done .dot   { background: var(--success); color: #fff; border-color: var(--success); }
.steps .stp.active .dot { background: var(--brand);   color: #fff; border-color: var(--brand); }
.steps .stp.active      { color: var(--text); font-weight: 620; }
.steps .stp.done        { color: var(--text-2); }
.steps .link { flex: 1; height: 1px; background: var(--border); margin: 0 10px; min-width: 18px; }

/* ── 键值行 ─────────────────────────────────────────── */
.kv { display: flex; justify-content: space-between; align-items: baseline;
      padding: 6px 0; font-size: 13px; border-bottom: 1px dashed var(--border); }
.kv:last-child { border-bottom: none; }
.kv .k { color: var(--text-3); }
.kv .v { color: var(--text); font-weight: 600; }

/* ── 分数环 ─────────────────────────────────────────── */
.ring-wrap { position: relative; display: inline-flex; align-items: center; justify-content: center; }
.ring-wrap .ring-val {
    position: absolute; font-weight: 720; line-height: 1;
    display: flex; flex-direction: column; align-items: center;
}
.ring-wrap .ring-cap { font-size: 11px; color: var(--text-3); font-weight: 500; margin-top: 3px; }

/* ── Streamlit 原生控件微调 ─────────────────────────── */
[data-testid="stSidebar"] { background: var(--surface); border-right: 1px solid var(--border); }
[data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }

.stButton > button {
    border-radius: 11px; font-weight: 650; font-size: 13px;
    border: 1px solid var(--border-2); transition: all .15s ease;
    min-height: 40px; padding-left: 12px; padding-right: 12px;
}
.stButton > button, .stButton > button * {
    white-space: nowrap !important;
    word-break: keep-all !important;
    overflow-wrap: normal !important;
}
.stButton > button:hover { border-color: var(--brand); color: var(--brand); }
.stButton > button[kind="primary"],
/* ★ Streamlit 把按钮文字包在内层 <p>/<div> 里，而全局的 `p{color:var(--text-2)}`
   会盖掉按钮自己的 color —— 表现为"紫底上一行看不见的深色字"。
   必须显式给后代元素上色，只写在 button 上不够。 */
.stButton > button[kind="primary"] * {
    color: #fff !important;
}
.stButton > button[kind="primary"] {
    background: var(--brand); border-color: var(--brand);
}
.stButton > button[kind="primary"]:hover { background: var(--brand-600); border-color: var(--brand-600); }
/* 禁用态要一眼看得出来，否则用户会以为按钮坏了 */
.stButton > button:disabled,
.stButton > button:disabled * {
    background: var(--surface-3) !important; color: var(--text-3) !important;
    border-color: var(--border) !important; cursor: not-allowed;
}

/* 侧边栏动作按钮 */
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    min-height: 36px;
    padding: 0 6px !important;
    display: flex; align-items: center; justify-content: center;
    font-size: 12.5px; line-height: 1; white-space: nowrap;
}
[data-testid="stSidebar"] .stButton > button p {
    margin: 0 !important; padding: 0 !important; line-height: 1 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: var(--surface-3);
}

[data-testid="stFileUploader"] {
    background: var(--surface); border: 1px dashed var(--border-2);
    border-radius: 16px; padding: 10px 14px;
}
[data-testid="stFileUploader"]:hover { border-color: var(--brand); }

/* 选中标签使用品牌青绿色时，强制保持白字，避免被全局文字色覆盖。 */
[data-testid="stMultiSelect"] [data-baseweb="tag"],
[data-testid="stMultiSelect"] [data-baseweb="tag"] span {
    color: #fff !important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"] svg { fill: #fff !important; }

.streamlit-expanderHeader, [data-testid="stExpander"] summary {
    font-size: 13px; font-weight: 600; color: var(--text);
}
[data-testid="stExpander"] {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 16px; box-shadow: var(--shadow);
}

[data-testid="stMetricValue"] { font-size: 22px; font-weight: 680; }

/* ── 顶部产品栏 ─────────────────────────────────────── */
.top-shell {
    display: flex; align-items: center; justify-content: space-between;
    gap: 24px; padding: 16px 20px 14px; margin-bottom: 0;
    background: #fff; border: 1px solid var(--border);
    border-radius: 13px 13px 0 0; box-shadow: var(--shadow);
    border-bottom-color:#edf3f3;
}
.top-brand { display:flex;align-items:center;gap:13px; }
.top-brand .brand-mark {
    width: 40px; height: 40px; border-radius: 11px;
    background: var(--brand); color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 800; letter-spacing: .04em;
}
.top-brand strong { display:block;color:var(--text);font-size:24px;line-height:1.18;letter-spacing:-.025em; }
.top-brand small { display:block;color:var(--text-3);font-size:11px;margin-top:4px; }
.top-actions { display:flex;align-items:center;gap:8px;color:var(--text-2);font-size:12px; }
.top-actions b { margin-left:10px;padding:6px 10px;border:1px solid var(--border);border-radius:8px;color:var(--text-2);background:#fff; }
.mock-dot { width:8px;height:8px;border-radius:50%;background:#22c55e;box-shadow:0 0 0 4px #dcfce7; }
.workflow-note { display:none; }

/* ── 主导航：把 radio 变成分段控件 ──────────────────────
   ★ 必须继续用 st.radio 而不是 st.tabs()：实测 tabs 无法用代码切换，
     而"查看评估报告"这类按钮需要跳到别的页。问题从来不是选错组件，
     而是它默认长得像一组单选框。 */
div[data-testid="stRadio"]:has([data-testid="stRadioGroup"][aria-label="主流程"]) {
    width:100%!important;box-sizing:border-box;
    background:#fff;border:1px solid var(--border);border-top:0;border-radius:0 0 13px 13px;
    padding:7px 12px 9px;margin-bottom:10px;box-shadow:0 8px 20px rgba(23,62,88,.06);
}
div[data-testid="stRadio"]:has([data-testid="stRadioGroup"][aria-label="主流程"]) > div[role="radiogroup"] {
    gap: 4px; background: transparent; padding: 0;
    border-radius: 9px; display: flex; width:100%;
}
div[data-testid="stElementContainer"]:has(> div[data-testid="stRadio"] [aria-label="主流程"]) {
    width:100%!important;
}
div[data-testid="stRadio"]:has([data-testid="stRadioGroup"][aria-label="主流程"]) [data-testid="stRadioOption"] {
    flex:0 0 auto;padding: 10px 25px; border-radius: 9px; margin: 0;
    font-size: 16px; font-weight: 680; color: var(--text-2);
    cursor: pointer; transition: all .15s ease;
}
div[data-testid="stRadio"]:has([data-testid="stRadioGroup"][aria-label="主流程"]) [data-testid="stRadioOption"]:hover {
    background: var(--brand-50); color: var(--text);
}
div[data-testid="stRadio"]:has([data-testid="stRadioGroup"][aria-label="主流程"]) [data-testid="stRadioOption"][data-selected="true"] {
    background: var(--brand); color: #fff; box-shadow: none;
}
div[data-testid="stRadio"]:has([data-testid="stRadioGroup"][aria-label="主流程"]) [data-testid="stRadioOption"][data-selected="true"] * { color:#fff!important; }
/* 隐藏原生圆点，只留文字 */
div[data-testid="stRadio"]:has([data-testid="stRadioGroup"][aria-label="主流程"]) [data-testid="stRadioOption"] > div > div > div:first-child { display:none!important; }

/* 模块一内部流程：覆盖 Streamlit 分段控件的默认紫色。 */
.st-key-screening_stage [role="radiogroup"],
.st-key-risk_stage [role="radiogroup"] {
    border-color:var(--border-2)!important;
    background:var(--surface-2)!important;
}
.st-key-screening_stage button[data-variant="segmented_control"],
.st-key-risk_stage button[data-variant="segmented_control"] {
    border-color:transparent!important;
    color:var(--text-2)!important;
    box-shadow:none!important;
}
.st-key-screening_stage button[data-variant="segmented_control"][data-selected="true"],
.st-key-risk_stage button[data-variant="segmented_control"][data-selected="true"] {
    background:var(--brand)!important;
    border-color:var(--brand)!important;
}
.st-key-screening_stage button[data-variant="segmented_control"][data-selected="true"] *,
.st-key-risk_stage button[data-variant="segmented_control"][data-selected="true"] * {
    color:#fff!important;
}

/* 每个模块只有一张主工作区卡片，岗位筛选、页签和业务内容都收进来。 */
[class*="st-key-hirex_workspace_"] {
    background:#fff;
    border:1px solid var(--border)!important;
    border-radius:18px!important;
    box-shadow:0 10px 30px rgba(23,62,88,.07)!important;
}
[class*="st-key-hirex_workspace_"] > [data-testid="stVerticalBlock"] {
    gap:.65rem;
}

/* ── 对话气泡 ───────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 12px 14px; margin-bottom: 10px;
    box-shadow: var(--shadow);
}
[data-testid="stChatMessage"] p { color: var(--text); line-height: 1.65; }

hr { border-color: var(--border); margin: 20px 0; }

[data-testid="stDataFrame"], [data-testid="stPlotlyChart"] {
    background:#fff;border:1px solid var(--border);border-radius:18px;
    box-shadow:var(--shadow);overflow:hidden;padding:4px;
}

@media(max-width:900px){
  .top-actions{display:none}.workflow-note{text-align:left}.block-container{padding-left:1rem;padding-right:1rem}
  div[data-testid="stRadio"]:has([data-testid="stRadioGroup"][aria-label="主流程"]) > div[role="radiogroup"]{display:flex;overflow-x:auto}
  div[data-testid="stRadio"]:has([data-testid="stRadioGroup"][aria-label="主流程"]) [data-testid="stRadioOption"]{padding:8px 12px;white-space:nowrap}
}
</style>
"""

CSS = _CSS_TEMPLATE.replace("/*__TOKENS__*/", _vars())


def inject_theme() -> None:
    """在页面最顶部调用一次。"""
    st.markdown(CSS, unsafe_allow_html=True)
