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
    "brand":        "#4f46e5",
    "brand-600":    "#4338ca",
    "brand-50":     "#eef2ff",
    "brand-100":    "#e0e7ff",
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
    "text":         "#0f172a",
    "text-2":       "#475569",
    "text-3":       "#94a3b8",
    "surface":      "#ffffff",
    "surface-2":    "#f8fafc",
    "surface-3":    "#f1f5f9",
    "border":       "#e2e8f0",
    "border-2":     "#cbd5e1",
    # 形状
    "radius":       "10px",
    "radius-lg":    "14px",
    "shadow":       "0 1px 2px rgba(15,23,42,.04), 0 1px 3px rgba(15,23,42,.06)",
    "shadow-md":    "0 4px 6px -1px rgba(15,23,42,.07), 0 2px 4px -2px rgba(15,23,42,.05)",
}

# 面试题五个维度的配色，题卡与统计图共用一套
DIMENSION_COLORS = {
    "技术基础":   "#4f46e5",
    "项目深挖":   "#059669",
    "场景设计":   "#d97706",
    "行为面试":   "#db2777",
    "模糊点追问": "#7c3aed",
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
.stApp { background: var(--surface-2); }

/* ★ padding-top 必须留出 Streamlit 自带顶栏的高度。
   实测：[data-testid="stHeader"] 高 60px、position:absolute、z-index 999990，
   而且【背景是不透明白色】。我一开始把 padding-top 压到 1.2rem(19.2px)，
   品牌条的 top 就落到 35px —— 正好钻到顶栏底下被盖住，
   而顶栏是 absolute 定位在滚动容器顶部的，所以**往上滑也露不出来**，
   表现为"那几行字只有一半"。60px + 呼吸空间 = 4.75rem。 */
.block-container { padding-top: 4.75rem; padding-bottom: 3rem; max-width: 1320px; }

/* 顶栏本身也对齐一下配色，否则白条压在浅灰页面上有一道明显的色差 */
[data-testid="stHeader"] { background: var(--surface-2); }

h1, h2, h3, h4 { color: var(--text); font-weight: 650; letter-spacing: -0.01em; }
p, li, span, label { color: var(--text-2); }
a { color: var(--brand); }

/* ── 页头 ──────────────────────────────────────────── */
.pg-head {
    display: flex; align-items: center; gap: 14px;
    padding: 18px 22px; margin-bottom: 18px;
    background: linear-gradient(135deg, #ffffff 0%, var(--brand-50) 100%);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow);
}
.pg-head .pg-icon {
    width: 42px; height: 42px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    background: var(--brand); color: #fff;
    border-radius: 11px; font-size: 20px;
}
.pg-head .pg-title { font-size: 20px; font-weight: 680; color: var(--text); line-height: 1.25; }
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
.stat-grid { display: grid; gap: 12px; margin: 14px 0 4px; }
.stat-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 14px 16px; box-shadow: var(--shadow);
}
.stat-card .sc-label { font-size: 12px; color: var(--text-3); margin-bottom: 5px; }
.stat-card .sc-value { font-size: 21px; font-weight: 680; color: var(--text); line-height: 1.15; }
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
.pill.brand   { color: var(--brand);   background: var(--brand-50);   border-color: #c7d2fe; }
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
    border-radius: 8px; font-weight: 600; font-size: 13px;
    border: 1px solid var(--border-2); transition: all .15s ease;
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

/* ── 侧边栏里的小动作按钮（Skills 的 停用 / 激活）─────────────
   原来点不中，是三件事叠加的：
     1. 按钮所在列只占 1/8 宽（st.columns([2,5,1])），侧边栏本来就窄,
        算下来实际可点区域只有十几像素；
     2. Streamlit 的按钮内层是 <p>，继承了全局 p 的行高与 margin，
        单字符 ✕ 在盒子里偏上，看着"不居中"；
     3. 图标按钮本身就比文字按钮难点 —— 已把 ✕/＋ 换成「停用」「激活」,
        既是更大的点击目标，也不用猜 ✕ 是停用还是删除。
   列宽已在 integration.py 调整，这里负责让按钮把列吃满并真正居中。
   min-height 36px 对着鼠标绰绰有余，也不至于把侧边栏撑得太松。 */
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    min-height: 36px;
    padding: 0 6px !important;
    display: flex; align-items: center; justify-content: center;
    font-size: 12.5px; line-height: 1; white-space: nowrap;
}
/* 内层 <p> 自带 margin/line-height，会把字符顶偏 —— 必须一起清掉,
   只在 button 上设 flex 居中是不够的。 */
[data-testid="stSidebar"] .stButton > button p {
    margin: 0 !important; padding: 0 !important; line-height: 1 !important;
}
/* hover 给个底色，让"我正指在这颗按钮上"看得见 —— 窄侧边栏里相邻按钮
   挨得近，只靠文字变色不够明显。刻意不用红色：停用可以再激活，不是
   破坏性动作，红色留给真正的删除（在「🧩 Skills」页）。 */
[data-testid="stSidebar"] .stButton > button:hover {
    background: var(--surface-3);
}

[data-testid="stFileUploader"] {
    background: var(--surface); border: 1px dashed var(--border-2);
    border-radius: var(--radius); padding: 6px 12px;
}
[data-testid="stFileUploader"]:hover { border-color: var(--brand); }

.streamlit-expanderHeader, [data-testid="stExpander"] summary {
    font-size: 13px; font-weight: 600; color: var(--text);
}
[data-testid="stExpander"] {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); box-shadow: var(--shadow);
}

[data-testid="stMetricValue"] { font-size: 22px; font-weight: 680; }

/* ── 顶部品牌条 ─────────────────────────────────────── */
.brand-bar {
    display: flex; align-items: center; justify-content: space-between;
    gap: 16px; padding: 10px 18px; margin-bottom: 12px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); box-shadow: var(--shadow);
}
.brand-bar .brand-left { display: flex; align-items: center; gap: 10px; }
.brand-bar .brand-mark {
    width: 26px; height: 26px; border-radius: 7px;
    background: var(--brand); color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; letter-spacing: .02em;
}
.brand-bar .brand-name { font-size: 15px; font-weight: 680; color: var(--text); }
.brand-bar .brand-flow { display: flex; align-items: center; gap: 7px; font-size: 12px; }
.brand-bar .flow-step  { color: var(--text-3); }
.brand-bar .flow-arrow { color: var(--border-2); }

/* ── 主导航：把 radio 变成分段控件 ──────────────────────
   ★ 必须继续用 st.radio 而不是 st.tabs()：实测 tabs 无法用代码切换，
     而"查看评估报告"这类按钮需要跳到别的页。问题从来不是选错组件，
     而是它默认长得像一组单选框。 */
div[data-testid="stRadio"] > div[role="radiogroup"] {
    gap: 4px; background: var(--surface-3); padding: 4px;
    border-radius: 10px; display: inline-flex;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label {
    padding: 6px 16px; border-radius: 7px; margin: 0;
    font-size: 13px; font-weight: 600; color: var(--text-2);
    cursor: pointer; transition: all .15s ease;
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label:hover {
    background: rgba(255,255,255,.7); color: var(--text);
}
div[data-testid="stRadio"] > div[role="radiogroup"] > label:has(input:checked) {
    background: var(--surface); color: var(--brand);
    box-shadow: var(--shadow);
}
/* 隐藏原生圆点，只留文字 */
div[data-testid="stRadio"] > div[role="radiogroup"] > label > div:first-child { display: none; }

/* ── 对话气泡 ───────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 12px 14px; margin-bottom: 10px;
    box-shadow: var(--shadow);
}
[data-testid="stChatMessage"] p { color: var(--text); line-height: 1.65; }

hr { border-color: var(--border); margin: 20px 0; }
</style>
"""

CSS = _CSS_TEMPLATE.replace("/*__TOKENS__*/", _vars())


def inject_theme() -> None:
    """在页面最顶部调用一次。"""
    st.markdown(CSS, unsafe_allow_html=True)
