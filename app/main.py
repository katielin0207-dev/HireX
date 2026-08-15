"""
Streamlit 统一前端：AI 智能招聘系统 v2.1
专业级 UI 设计 — 简历分析 → AI面试 → 评估报告
"""
import streamlit as st
import streamlit.components.v1 as components
import json, os, sys, time, hashlib, random
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import settings
from app.parser import parse_uploaded_file

# ── New Architecture (v2.2): Harness/Graph/Checker/Skills/Flywheel ──
try:
    from app.integration import (
        run_analysis_with_pipeline,
        render_skills_panel,
        render_checker_panel,
        render_graph_panel,
        render_flywheel_panel,
    )
    NEW_ARCH_ENABLED = True
except Exception:
    NEW_ARCH_ENABLED = False

import nest_asyncio
nest_asyncio.apply()

# ── Page Config ─────────────────────────────────────
st.set_page_config(
    page_title="AI 招聘系统",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="auto",
)

# ── 主题与视图层 ─────────────────────────────────────
# ★ 原来这里是一段 480 行的 <style>，与业务逻辑混在同一个文件里。
#   现已抽到 app/ui/theme.py，作为视图层唯一的样式来源。
from app.ui import inject_theme
from app.views import analysis as view_analysis
from app.views import interview as view_interview
from app.views import interview_eval as view_interview_eval
from app.views import report as view_report
from app.views import screening as view_screening
from app.views import risk as view_risk

inject_theme()


# ── Session State Init ──────────────────────────────
DEFAULTS = {
    "analysis_done": False, "jd_text": "", "resume_text": "",
    "jd_data": {}, "resume_data": {}, "match_result": {},
    "all_questions": [], "ambiguity_followups": [],
    "selected_questions": [], "remaining_pool": [],
    "interview_started": False, "interviewer": None,
    "chat_messages": [], "interview_done": False,
    "report_data": {}, "tts_enabled": False,
    "tts_engine": "edge-tts (免费)", "tts_voice": "云扬 (专业男声)",
    "tts_error": "", "tts_notice": "",   # 语音失败/降级提示，由侧边栏消费后清空
    "digital_human_enabled": True,
    "n_rounds": settings.DEFAULT_SAMPLE_ROUNDS,
    "active_tab": "screening", "ui_lang": "zh",
    "interview_link_info": None,   # 面试链接信息 {token, link, ...}
    "voice_input_text": "",        # 语音识别的文本
}
for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val



def render_digital_human(speak_text="", persona_name="面试官", w=220, h=290):
    """专业 SVG 虚拟面试官形象 — 西装半身，嘴部随语音开合，眨眼联动"""
    mute = st.session_state.get("tts_enabled", False)
    mute_js = "false" if mute else "true"
    # 角色配色（支持多角色扩展，当前统一：深蓝西装+白衬衫+领带）
    suit_color = "#1e2240"
    shirt_color = "#f5f0eb"
    tie_color = "#818cf8"
    skin_color = "#edd9c4"
    hair_color = "#2a1f14"

    html_str = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{
  background:#1a1d27;display:flex;flex-direction:column;align-items:center;
  justify-content:center;height:100%;overflow:hidden;font-family:system-ui,sans-serif;
}}
.svg-wrap{{position:relative;width:{w}px;height:{h-32}px;}}
.name-tag{{
  color:#9aa0b0;font-size:11px;text-align:center;margin-top:6px;
  letter-spacing:0.5px;
}}
/* CSS 呼吸动画 */
@keyframes breathe{{
  0%,100%{{transform:translateY(0);}}
  50%{{transform:translateY(-1.5px);}}
}}
@keyframes blinkE {{
  0%,90%,100%{{ry:8.5;}}
  93%{{ry:1.5;}}
}}
@keyframes blinkPupil {{
  0%,90%,100%{{ry:3.8;opacity:1;}}
  93%{{ry:0.5;opacity:0.3;}}
}}
.breath{{animation:breathe 3.5s ease-in-out infinite;}}
.eye-l{{animation:blinkE 4s ease-in-out infinite;}}
.eye-r{{animation:blinkE 4s ease-in-out 0.15s infinite;}}
.pupil-l{{animation:blinkPupil 4s ease-in-out infinite;}}
.pupil-r{{animation:blinkPupil 4s ease-in-out 0.15s infinite;}}
</style></head><body>
<div class="svg-wrap breath">
<svg viewBox="0 0 220 260" width="220" height="260" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="glow" cx="50%" cy="35%" r="50%">
      <stop offset="0%" stop-color="rgba(99,102,241,0.12)"/>
      <stop offset="100%" stop-color="rgba(99,102,241,0)"/>
    </radialGradient>
    <radialGradient id="cheekL" cx="30%" cy="58%">
      <stop offset="0%" stop-color="rgba(233,150,140,0.2)"/>
      <stop offset="100%" stop-color="rgba(237,217,196,0)"/>
    </radialGradient>
    <radialGradient id="cheekR" cx="70%" cy="58%">
      <stop offset="0%" stop-color="rgba(233,150,140,0.2)"/>
      <stop offset="100%" stop-color="rgba(237,217,196,0)"/>
    </radialGradient>
    <linearGradient id="hairGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#3d2b18"/>
      <stop offset="100%" stop-color="#1a1008"/>
    </linearGradient>
    <filter id="softShadow">
      <feDropShadow dx="0" dy="2" stdDeviation="3" flood-opacity="0.25"/>
    </filter>
  </defs>

  <!-- Background glow -->
  <ellipse cx="110" cy="90" rx="95" ry="120" fill="url(#glow)"/>

  <!-- === 身体 / 西装 === -->
  <!-- 肩膀轮廓 -->
  <path d="M30,200 Q20,175 28,150 L52,130 L168,130 L192,150 Q200,175 190,200"
        fill="{suit_color}" stroke="#151a30" stroke-width="0.5"/>
  <!-- 肩部线条 -->
  <path d="M28,150 Q35,165 45,175 L110,172 L175,175 Q185,165 192,150"
        fill="none" stroke="#252d4a" stroke-width="1"/>
  <!-- 翻领左 -->
  <path d="M56,132 L75,175 Q85,180 100,170 L110,145 Z" fill="#252d4a"/>
  <!-- 翻领右 -->
  <path d="M164,132 L145,175 Q135,180 120,170 L110,145 Z" fill="#252d4a"/>

  <!-- 衬衫 V 领 -->
  <path d="M88,134 L95,178 L110,188 L125,178 L132,134 Z" fill="{shirt_color}"/>
  <!-- 衬衫中线 -->
  <line x1="110" y1="136" x2="110" y2="175" stroke="#e0d5c5" stroke-width="0.5"/>

  <!-- 领带 -->
  <path d="M102,108 L118,108 L116,145 L112,148 L110,188 L108,148 L104,145 Z" fill="{tie_color}"/>
  <!-- 领带结 -->
  <path d="M104,108 L116,108 L112,100 L108,100 Z" fill="{tie_color}"/>
  <!-- 领带高光 -->
  <line x1="110" y1="102" x2="110" y2="170" stroke="rgba(255,255,255,0.08)" stroke-width="2"/>

  <!-- === 颈部 === -->
  <path d="M96,82 Q108,90 110,90 Q112,90 124,82 L128,135 L92,135 Z" fill="{skin_color}"/>
  <!-- 颈部阴影 -->
  <ellipse cx="110" cy="130" rx="16" ry="4" fill="rgba(180,150,130,0.3)"/>

  <!-- === 头部 === -->
  <!-- 脸型（椭圆+下巴） -->
  <path d="M65,75 Q65,35 90,18 Q110,12 130,18 Q155,35 155,75 Q158,100 145,118 Q130,132 110,134 Q90,132 75,118 Q62,100 65,75 Z"
        fill="{skin_color}" filter="url(#softShadow)"/>
  <!-- 脸颊红晕 -->
  <ellipse cx="85" cy="90" rx="18" ry="12" fill="url(#cheekL)"/>
  <ellipse cx="135" cy="90" rx="18" ry="12" fill="url(#cheekR)"/>

  <!-- 耳朵 -->
  <ellipse cx="62" cy="78" rx="6" ry="11" fill="{skin_color}" stroke="rgba(190,160,135,0.5)" stroke-width="0.5"/>
  <ellipse cx="158" cy="78" rx="6" ry="11" fill="{skin_color}" stroke="rgba(190,160,135,0.5)" stroke-width="0.5"/>
  <!-- 耳朵内部 -->
  <ellipse cx="62" cy="78" rx="3.5" ry="7" fill="rgba(210,175,150,0.5)"/>
  <ellipse cx="158" cy="78" rx="3.5" ry="7" fill="rgba(210,175,150,0.5)"/>

  <!-- === 头发 === -->
  <!-- 后发 -->
  <path d="M60,72 Q55,40 75,20 Q95,8 110,7 Q125,8 145,20 Q165,40 160,72
           Q162,50 140,28 Q120,15 110,14 Q100,15 80,28 Q58,50 60,72 Z"
        fill="{hair_color}" opacity="0.6"/>
  <!-- 主发（波浪M字刘海） -->
  <path d="M58,70 Q56,40 68,24 Q80,10 98,8 L100,18 Q90,22 82,32 Q70,48 66,70 Z"
        fill="url(#hairGrad)"/>
  <path d="M162,70 Q164,40 152,24 Q140,10 122,8 L120,18 Q130,22 138,32 Q150,48 154,70 Z"
        fill="url(#hairGrad)"/>
  <!-- 顶发 -->
  <path d="M70,22 Q80,10 95,6 L105,6 L110,5 L115,6 L125,6 Q140,10 150,22
           Q145,14 130,8 Q115,5 110,6 Q105,5 90,8 Q75,14 70,22 Z"
        fill="url(#hairGrad)"/>
  <!-- 刘海 -->
  <path d="M66,48 Q68,36 78,28 Q85,22 92,26 L96,42 Q86,38 78,44 Q70,48 66,56 Z"
        fill="#352816"/>
  <path d="M154,48 Q152,36 142,28 Q135,22 128,26 L124,42 Q134,38 142,44 Q150,48 154,56 Z"
        fill="#352816"/>
  <path d="M92,24 Q98,20 105,22 Q108,24 106,30 Q102,32 96,30 Q92,27 92,24 Z"
        fill="#2a1a0e"/>
  <path d="M128,24 Q122,20 115,22 Q112,24 114,30 Q118,32 124,30 Q128,27 128,24 Z"
        fill="#2a1a0e"/>

  <!-- === 眉毛 === -->
  <path d="M76,60 Q82,55 94,58" fill="none" stroke="#3d2b18" stroke-width="2.2" stroke-linecap="round"/>
  <path d="M144,60 Q138,55 126,58" fill="none" stroke="#3d2b18" stroke-width="2.2" stroke-linecap="round"/>

  <!-- === 眼睛 === -->
  <!-- 左眼 -->
  <ellipse class="eye-l" cx="90" cy="72" rx="9" ry="8.5" fill="#fff" stroke="#c0a890" stroke-width="0.8"/>
  <ellipse class="pupil-l" cx="90" cy="72" rx="5" ry="3.8" fill="#2a2218"/>
  <circle cx="88" cy="70" r="1.8" fill="#fff" opacity="0.8"/>
  <circle cx="91.5" cy="73" r="0.8" fill="#fff" opacity="0.4"/>
  <!-- 右眼 -->
  <ellipse class="eye-r" cx="130" cy="72" rx="9" ry="8.5" fill="#fff" stroke="#c0a890" stroke-width="0.8"/>
  <ellipse class="pupil-r" cx="130" cy="72" rx="5" ry="3.8" fill="#2a2218"/>
  <circle cx="128" cy="70" r="1.8" fill="#fff" opacity="0.8"/>
  <circle cx="131.5" cy="73" r="0.8" fill="#fff" opacity="0.4"/>
  <!-- 下眼睑 -->
  <path d="M82,79 Q90,83 98,79" fill="none" stroke="rgba(180,150,130,0.4)" stroke-width="0.5"/>
  <path d="M122,79 Q130,83 138,79" fill="none" stroke="rgba(180,150,130,0.4)" stroke-width="0.5"/>

  <!-- === 鼻子 === -->
  <path d="M108,76 Q106,82 105,92 Q104,96 107,98 Q110,100 113,98 Q116,96 115,92"
        fill="none" stroke="rgba(180,150,130,0.5)" stroke-width="0.8"/>
  <ellipse cx="110" cy="98" rx="4.5" ry="2.5" fill="rgba(180,150,130,0.2)"/>
  <!-- 鼻梁高光 -->
  <line x1="110" y1="74" x2="110" y2="90" stroke="rgba(255,255,255,0.08)" stroke-width="1.5"/>

  <!-- === 嘴巴（JS 动画控制开合）=== -->
  <path id="mouth" d="M98,112 Q110,120 122,112" fill="none" stroke="#d4856e" stroke-width="1.6" stroke-linecap="round"/>

  <!-- 下巴阴影 -->
  <ellipse cx="110" cy="128" rx="14" ry="3" fill="rgba(180,150,130,0.15)"/>
</svg>
</div>
<div class="name-tag">🎤 {persona_name}</div>
<script>
(function(){{
  var mouth=document.getElementById("mouth");
  var target=0, current=0;
  var openPaths=[
    "M98,112 Q110,119 122,112",
    "M97,113 Q110,121 123,113",
    "M96,114 Q110,123 124,114",
    "M95,115 Q110,125 125,115"
  ];
  var closedPath="M98,112 Q110,120 122,112";
  function updateMouth(){{
    current+=(target-current)*0.25;
    var idx=Math.min(Math.floor(current*openPaths.length),openPaths.length-1);
    if(current<0.05){{mouth.setAttribute("d",closedPath);}}
    else{{mouth.setAttribute("d",openPaths[idx]);}}
    requestAnimationFrame(updateMouth);
  }}
  if(!{mute_js}){{
    setInterval(function(){{target=Math.random()>0.5?Math.random()*0.55:0;}},150);
  }}
  updateMouth();
}})();
</script></body></html>"""
    components.html(html_str, height=h, scrolling=False)


# ── TTS 语音播报 ──────────────────────────────────────
def speak_text(text: str):
    """生成语音并存入 session_state 由页面播放。

    ★ 改动要点：**失败不再静默**。

    上一版这里有三层 except，把所有异常吞成 `audio_b64 = None`；
    而 tts_utils 里只把错误 print 到终端 —— Streamlit 界面上看不见。
    于是"没配讯飞凭证""网络不通""选了个根本不存在的引擎"三种情况，
    在用户眼里长得一模一样：**没声音，且不知道为什么**。

    现在统一走 tts_utils.synthesize()，它返回带原因的 TTSResult；
    失败或降级都写进 session_state，由侧边栏显示出来。
    """
    from app.tts_utils import get_voice_code, synthesize, ENGINE_EDGE

    engine = st.session_state.get("tts_engine", ENGINE_EDGE)
    voice_label = st.session_state.get("tts_voice", "云扬 (专业男声)")

    result = synthesize(text, engine=engine, voice=get_voice_code(voice_label))

    if result.ok:
        st.session_state["pending_audio_b64"] = result.audio_b64
        # 降级也要让人知道 —— 否则"听起来是好的"会掩盖配置根本没生效
        st.session_state["tts_notice"] = result.error if result.fell_back else ""
    else:
        st.session_state["pending_audio_b64"] = None
        st.session_state["tts_error"] = result.error or "语音合成失败（未知原因）"


def render_audio_player():
    """把待播音频渲染成 <audio>。

    ★ 必须是【函数】而不是模块级代码：候选人页走的是
      `page_candidate(); st.stop()` 这条分支，模块级的播放器在 st.stop()
      之后，**永远执行不到** —— 所以候选人端此前 100% 没有声音，
      哪怕合成成功也一样。现在候选人页自己调一次。
    """
    # 播放 pending_audio（由 speak_text 生成）
    #
    # ★ 自动播放**会被浏览器拦掉**，这是实测出来的，不是理论风险：
    #   全新未交互的标签页里 play() 抛 NotAllowedError
    #   （"play() failed because the user didn't interact with the document first"）。
    #   最典型的中招场景是**候选人打开面试链接**——页面一加载面试官就要开口，
    #   此时还没有任何点击。
    #
    #   而上一版渲染完 <audio> 就把 pending_audio_b64 清空了：播放被拦 → 没有声音、
    #   没有提示、音频还丢了。这恰好违反了本项目自己反复强调的那条原则 ——
    #   合成失败会报原因，**播放失败却是静默的**，用户眼里两者一模一样。
    #
    #   现在：先尝试自动播；被拦就把播放按钮显示出来，让人点一下就能听。
    audio_b64 = st.session_state.get("pending_audio_b64", "")
    if audio_b64:
        st.markdown(f"""
        <audio id="tts-player" autoplay style="display:none;">
            <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
        </audio>
        <div id="tts-fallback" style="display:none;margin:6px 0;padding:8px 12px;
             background:#fffbeb;border:1px solid #fde68a;border-radius:8px;font-size:13px;color:#92400e;">
          🔇 浏览器拦截了自动播放
          <button onclick="document.getElementById('tts-player').play();
                           this.parentElement.style.display='none';"
                  style="margin-left:8px;padding:3px 10px;border-radius:6px;border:1px solid #d97706;
                         background:#fff;color:#92400e;cursor:pointer;font-size:12px;">▶ 点击播放</button>
        </div>
        <script>
        (function() {{
          var a = document.getElementById('tts-player');
          if (!a) return;
          var p = a.play();
          if (p && p.catch) {{
            p.catch(function() {{
              var f = document.getElementById('tts-fallback');
              if (f) f.style.display = 'block';
            }});
          }}
        }})();
        </script>
        """, unsafe_allow_html=True)
        st.session_state["pending_audio_b64"] = ""



# ── Sidebar ──────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        _, col_c, _ = st.columns([1, 1, 1])
        with col_c:
            st.image("logo.png", width=60)
        
        st.markdown("---")
        
        # Model info
        st.markdown(f"""
        <div style="font-size:12px;color:var(--text-2);margin-bottom:16px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                <span>模型</span><span style="color:var(--primary-l);">{settings.LLM_MODEL}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                <span>TTS</span><span style="color:var(--primary-l);">{st.session_state.get("tts_engine", settings.TTS_ENGINE)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;">
                <span>面试轮数</span><span style="color:var(--primary-l);">{st.session_state.n_rounds}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Settings
        st.markdown("**⚙️ 设置**")
        n = st.slider("面试题数", 3, 15, st.session_state.n_rounds, key="sidebar_rounds")
        st.session_state.n_rounds = n
        st.session_state.tts_enabled = st.toggle("🔊 TTS 语音播报", st.session_state.tts_enabled)
        
        if st.session_state.tts_enabled:
            # ★ 只列【真正可用】的引擎。
            #   上一版把三个引擎写死在列表里，其中「XTTS 离线SDK」需要本地
            #   SDK/libs/64/AEE_lib.dll，而这个仓库里根本没有 SDK 目录 ——
            #   选了它必然静默无声。**一个选了什么都不会发生的选项，
            #   比没有这个选项糟得多**：用户会以为是自己操作错了。
            from app.tts_utils import engine_status, get_voice_options

            status = engine_status()
            engines = [n for n, ok, _ in status if ok]
            blocked = [(n, why) for n, ok, why in status if not ok]

            if not engines:
                st.warning("没有可用的语音引擎，语音播报已停用")
                st.session_state.tts_enabled = False
            else:
                cur_engine = st.session_state.get("tts_engine", engines[0])
                idx = engines.index(cur_engine) if cur_engine in engines else 0
                st.session_state["tts_engine"] = st.selectbox(
                    "语音引擎", engines, index=idx, key="sidebar_tts_engine",
                    help="仅列出当前环境真正可用的引擎",
                )

                # 不可用的也说清楚为什么 —— 让人知道"怎么才能用上"，
                # 而不是猜为什么少了一个选项
                if blocked:
                    with st.expander(f"另有 {len(blocked)} 个引擎不可用", expanded=False):
                        for name, why in blocked:
                            st.caption(f"**{name}** — {why}")

                options = get_voice_options(st.session_state["tts_engine"])
                if options:
                    voice_labels = [label for label, _ in options]
                    cur_voice = st.session_state.get("tts_voice", voice_labels[0])
                    if cur_voice not in voice_labels:
                        cur_voice = voice_labels[0]
                    st.session_state["tts_voice"] = st.selectbox(
                        "发音人", voice_labels,
                        index=voice_labels.index(cur_voice),
                        key="sidebar_tts_voice",
                    )

            # 上一次合成的失败/降级提示
            if st.session_state.get("tts_error"):
                st.error(f"🔇 {st.session_state['tts_error']}")
                st.session_state["tts_error"] = ""
            elif st.session_state.get("tts_notice"):
                st.info(f"🔉 {st.session_state['tts_notice']}")
                st.session_state["tts_notice"] = ""
        
        st.session_state.digital_human_enabled = st.toggle("👤 虚拟主播", st.session_state.digital_human_enabled)
        
        st.markdown("---")
        
        # Reset
        if st.button("🔄 重置会话", use_container_width=True):
            for key in DEFAULTS:
                st.session_state[key] = DEFAULTS[key]
            st.rerun()
        
        # Skills Management (New Architecture)
        if NEW_ARCH_ENABLED:
            st.markdown("---")
            render_skills_panel()
        
        # Footer
        # ★ 原来是 position:fixed —— 它脱离文档流后会【压在】下面的 Skills
        #   列表上（侧边栏本身是可滚动的，fixed 元素不跟着滚）。改成常规流。
        st.markdown(
            '<div style="margin-top:20px;padding-top:12px;border-top:1px solid var(--border);'
            'font-size:11px;color:var(--text-3);">MIT License · 2026</div>',
            unsafe_allow_html=True,
        )

# ── Voice Input Component ────────────────────────────
def voice_input_widget(key="voice_input"):
    """浏览器语音识别输入组件（Web Speech API）"""
    return st.components.v1.html(f"""
    <div id="voice-container-{key}" style="display:flex;align-items:center;gap:8px;">
        <button id="mic-btn-{key}" onclick="toggleVoice('{key}')"
            style="width:40px;height:40px;border-radius:50%;border:2px solid #6366f1;
            background:#1e1b4b;color:#a5b4fc;font-size:18px;cursor:pointer;
            display:flex;align-items:center;justify-content:center;transition:all 0.2s;"
            title="语音输入">
            🎤
        </button>
        <span id="status-{key}" style="font-size:12px;color:#94a3b8;"></span>
        <input type="hidden" id="result-{key}" value="">
    </div>
    <script>
    (function() {{
        var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        var isRecording = false;
        var recognition = null;

        function initRecognition() {{
            if (!recognition && SpeechRecognition) {{
                recognition = new SpeechRecognition();
                recognition.lang = 'zh-CN';
                recognition.interimResults = false;
                recognition.continuous = false;
                recognition.maxAlternatives = 1;

                recognition.onresult = function(event) {{
                    var transcript = event.results[0][0].transcript;
                    document.getElementById('result-{key}').value = transcript;
                    document.getElementById('mic-btn-{key}').innerHTML = '🎤';
                    document.getElementById('mic-btn-{key}').style.background = '#1e1b4b';
                    document.getElementById('status-{key}').textContent = '';
                    isRecording = false;

                    /* ★ 把识别结果送回 Python。
                       原来发的是 streamlit:setComponentValue —— 那个协议只对
                       用 components.declare_component 注册过的自定义组件有效；
                       st.components.v1.html() 渲染的是**静态 iframe**，没有
                       componentId，Streamlit 根本不监听它。
                       更直接的证据：st.components.v1.html() 的返回类型是
                       DeltaGenerator，压根不返回组件值 —— 所以
                       handle_voice_input() 里的 isinstance(val, str) 永远为假，
                       识别出来的文字从来没有到达过 Python。而且它失败得很安静：
                       麦克风会亮、会听、会识别，只是结果被丢掉。

                       改法：srcdoc iframe 与父页同源（已实测 window.parent.document
                       可访问），直接把文本写进候选人页的输入框，并派发 input 事件
                       让 React 记账 —— 用户看得见文字进了框，点发送即可。*/
                    try {{
                        var doc = window.parent.document;
                        var box = doc.querySelector('input[aria-label="candidate_text_input"]')
                               || [].slice.call(doc.querySelectorAll('input[type="text"]')).pop();
                        if (box) {{
                            var setter = Object.getOwnPropertyDescriptor(
                                window.parent.HTMLInputElement.prototype, 'value').set;
                            setter.call(box, transcript);
                            box.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            document.getElementById('status-{key}').textContent = '✅ 已填入，请点发送';
                        }} else {{
                            document.getElementById('status-{key}').textContent =
                                '⚠️ 识别到「' + transcript + '」但没找到输入框，请手动输入';
                        }}
                    }} catch (err) {{
                        document.getElementById('status-{key}').textContent =
                            '⚠️ 识别到「' + transcript + '」但无法回填：' + err.message;
                    }}
                }};

                recognition.onerror = function(event) {{
                    document.getElementById('status-{key}').textContent = '❌ ' + event.error;
                    document.getElementById('mic-btn-{key}').innerHTML = '🎤';
                    document.getElementById('mic-btn-{key}').style.background = '#1e1b4b';
                    isRecording = false;
                }};

                recognition.onend = function() {{
                    if (isRecording) {{
                        var statusEl = document.getElementById('status-{key}');
                        if (!statusEl.textContent.includes('❌')) {{
                            statusEl.textContent = '';
                        }}
                    }}
                    document.getElementById('mic-btn-{key}').innerHTML = '🎤';
                    document.getElementById('mic-btn-{key}').style.background = '#1e1b4b';
                    isRecording = false;
                }};
            }}
        }}

        window.toggleVoice = function(k) {{
            initRecognition();
            if (!recognition) {{
                document.getElementById('status-{key}').textContent = '⚠️ 浏览器不支持语音识别';
                return;
            }}
            if (isRecording) {{
                recognition.stop();
                isRecording = false;
                document.getElementById('mic-btn-{key}').innerHTML = '🎤';
                document.getElementById('mic-btn-{key}').style.background = '#1e1b4b';
                document.getElementById('status-{key}').textContent = '';
            }} else {{
                try {{
                    recognition.start();
                    isRecording = true;
                    document.getElementById('mic-btn-{key}').innerHTML = '🔴';
                    document.getElementById('mic-btn-{key}').style.background = '#ef4444';
                    document.getElementById('status-{key}').textContent = '正在聆听...';
                }} catch(e) {{
                    document.getElementById('status-{key}').textContent = '⚠️ ' + e.message;
                }}
            }}
        }};
    }})();
    </script>
    """, height=60)

def handle_voice_input():
    """渲染语音输入组件。

    ★ 这里【不再尝试读返回值】：st.components.v1.html() 返回的是
      DeltaGenerator，不是组件值 —— 上一版 `if val and isinstance(val, str)`
      的条件永远为假，是一段看着在工作、实际什么也不做的代码。
      识别结果现在由组件内部直接写进页面上的输入框（见 voice_input_widget）。
    """
    voice_input_widget()
    return None

# ── Candidate Interview Page ──────────────────────────
def page_candidate():
    """候选人独立面试页面（通过链接访问）"""
    from app.interview_link import get_interview, deactivate_interview
    from app.interviewer import InterviewerAgent, InterviewState

    token = st.session_state.get("candidate_token", "")
    interview_info = get_interview(token)

    if not interview_info:
        st.markdown("""
        <div style="text-align:center;padding:80px 20px;">
            <div style="font-size:64px;margin-bottom:20px;">⏰</div>
            <h2 style="color:var(--text);">链接已过期或不存在</h2>
            <p style="color:var(--text-2);font-size:14px;">请向面试官索取新的面试链接</p>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Candidate CSS ──
    st.markdown("""
    <style>
    .candidate-header {
        text-align:center;padding:30px 20px 10px;
        background:linear-gradient(135deg,rgba(99,102,241,0.08),rgba(139,92,246,0.04));
        border-bottom:1px solid rgba(99,102,241,0.1);margin-bottom:20px;
    }
    .candidate-header h1 { font-size:24px;color:var(--text);margin:0; }
    .candidate-header p { color:var(--text-2);font-size:13px;margin:4px 0 0; }
    .candidate-msg { font-size:14px;line-height:1.7;color:var(--text); }
    .candidate-msg.interviewer { background:rgba(99,102,241,0.06);padding:12px 16px;border-radius:12px;border:1px solid rgba(99,102,241,0.1);margin:8px 0; }
    .candidate-msg.candidate { background:rgba(16,185,129,0.06);padding:12px 16px;border-radius:12px;border:1px solid rgba(16,185,129,0.1);margin:8px 0; }
    .interview-ended {
        text-align:center;padding:40px 20px;
        background:linear-gradient(135deg,rgba(16,185,129,0.06),rgba(99,102,241,0.04));
        border-radius:16px;margin:20px 0;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Header ──
    st.markdown(f"""
    <div class="candidate-header">
        <h1>🤖 AI 面试</h1>
        <p>{interview_info['jd_title']} · 面试官：{interview_info['persona_name']}</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Init candidate state ──
    for ck in ("candidate_name", "candidate_started", "candidate_agent", "candidate_messages", "candidate_done"):
        if ck not in st.session_state:
            st.session_state[ck] = None if ck == "candidate_agent" else ("" if ck == "candidate_name" else ([] if ck == "candidate_messages" else False))

    # ── Step 1: Name input ──
    if not st.session_state.candidate_name:
        st.markdown("""
        <div style="text-align:center;padding:40px 20px;">
            <div style="font-size:48px;margin-bottom:16px;">👋</div>
            <h3>欢迎参加面试</h3>
            <p style="color:var(--text-2);">请输入你的姓名开始面试</p>
        </div>
        """, unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            name = st.text_input("你的姓名", placeholder="请输入姓名...", label_visibility="collapsed")
            if st.button("✅ 开始面试", type="primary", use_container_width=True, disabled=not name.strip()):
                st.session_state.candidate_name = name.strip()
                st.rerun()
        return

    # ── Step 2: Initialize Agent ──
    if not st.session_state.candidate_started:
        config = interview_info.get("interview_config", {})
        with st.spinner(f"正在准备面试..."):
            max_r = interview_info.get("max_rounds", 6)
            agent = InterviewerAgent(max_rounds=max_r)
            agent.load_parsed_data(
                config.get("jd_data", {}),
                config.get("resume_data", {}),
            )
            agent.initialize_persona()
            # 注入题库
            selected = config.get("selected_questions", [])
            remaining = config.get("remaining_pool", [])
            if selected:
                agent.inject_questions(selected, remaining)
            greeting, first_q = agent.generate_opening()
            # 个性化开场
            greeting = greeting.replace("候选人", st.session_state.candidate_name)
            greeting = greeting.replace("您好", f"{st.session_state.candidate_name}，您好")
            st.session_state.candidate_messages = [
                {"role": "interviewer", "content": f"{greeting}"},
            ]
            if first_q:
                st.session_state.candidate_messages.append(
                    {"role": "interviewer", "content": first_q}
                )
            st.session_state.candidate_agent = agent
            st.session_state.candidate_started = True
            # ★ 面试官要出声。原来候选人页从头到尾没调过 speak_text ——
            #   "面试官会说话"这件事在面试者那一端是完全不存在的。
            if st.session_state.get("tts_enabled", True) and first_q:
                speak_text(first_q)
            st.rerun()

    # ── Step 3: Interview chat ──
    agent = st.session_state.candidate_agent

    # ★ 播放器必须在这里调一次：模块级那个在 `page_candidate(); st.stop()`
    #   之后，候选人页根本走不到。
    render_audio_player()

    # ★ 数字人 + 语音开关。原来候选人页两样都没有 ——
    #   而"面试官有形象、会说话"恰恰是面试者那一端才需要看到的东西。
    col_dh, col_chat = st.columns([1, 3], gap="large")
    with col_dh:
        if st.session_state.get("digital_human_enabled", True):
            last_itv = next((m["content"] for m in reversed(st.session_state.candidate_messages)
                             if m["role"] == "interviewer"), "")
            render_digital_human(last_itv, interview_info.get("persona_name", "面试官"))
        st.session_state.tts_enabled = st.toggle(
            "🔊 面试官语音", value=st.session_state.get("tts_enabled", True),
            key="cand_tts", help="关掉就只看文字")
        if st.session_state.get("tts_error"):
            st.error(f"🔇 {st.session_state['tts_error']}")
            st.session_state["tts_error"] = ""
        elif st.session_state.get("tts_notice"):
            st.caption(f"🔉 {st.session_state['tts_notice']}")
            st.session_state["tts_notice"] = ""

    with col_chat:
        _render_candidate_chat(agent, token, deactivate_interview)


def _render_candidate_chat(agent, token, deactivate_interview):
    # Display messages
    for msg in st.session_state.candidate_messages:
        cls = "interviewer" if msg["role"] == "interviewer" else "candidate"
        icon = "🤖" if msg["role"] == "interviewer" else "👤"
        st.markdown(f"""
        <div class="candidate-msg {cls}">
            <strong>{icon} {'AI面试官' if msg['role'] == 'interviewer' else st.session_state.candidate_name}</strong><br>
            {msg['content']}
        </div>
        """, unsafe_allow_html=True)

    if st.session_state.candidate_done:
        st.markdown(f"""
        <div class="interview-ended">
            <div style="font-size:48px;">🎉</div>
            <h3>面试结束！</h3>
            <p style="color:var(--text-2);">感谢 {st.session_state.candidate_name} 的参与，面试结果已记录。</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("关闭页面", use_container_width=True):
            deactivate_interview(token)
            st.balloons()
        return

    # ── Voice + Text Input ──
    st.markdown("---")
    st.markdown("**💬 输入你的回答：**")

    # Voice input
    voice_text = handle_voice_input()
    if voice_text:
        st.session_state.voice_input_text = voice_text

    # Text input
    col_v, col_t = st.columns([1, 5])
    with col_v:
        pass  # voice widget already rendered via handle_voice_input above
    with col_t:
        user_input = st.text_input("", key="candidate_text_input",
                                   placeholder="输入回答，或点击 🎤 语音输入...",
                                   label_visibility="collapsed")

    submit_col, voice_status_col = st.columns([2, 3])
    with submit_col:
        submit = st.button("📨 发送回答", type="primary", use_container_width=True)
    with voice_status_col:
        if st.session_state.get("voice_input_text"):
            st.caption(f"🎤 语音识别: _{st.session_state.voice_input_text}_")

    final_input = user_input or st.session_state.get("voice_input_text", "")

    if submit and final_input.strip():
        # Process answer
        result = agent.process_answer(final_input.strip())
        st.session_state.candidate_messages.append(
            {"role": "candidate", "content": final_input.strip()}
        )
        if result["interview_ongoing"]:
            next_msg = result["message"]
            st.session_state.candidate_messages.append(
                {"role": "interviewer", "content": next_msg}
            )
            if st.session_state.get("tts_enabled", True) and next_msg:
                speak_text(next_msg)          # ★ 每一轮追问都要出声，不只是开场
        else:
            st.session_state.candidate_messages.append(
                {"role": "interviewer", "content": result.get("message", "面试结束")}
            )
            st.session_state.candidate_done = True
            deactivate_interview(token)
            # Save interview data for admin review
            st.session_state._last_candidate_data = agent.get_interview_data()
        # Clear voice input
        st.session_state.voice_input_text = ""
        st.rerun()

# ── 三个主页面：只做路由，渲染在 app/views/ ────────────
# ★ 改造前这三个函数各自几百行，全部挤在 main.py（2156 行）里，
#   页头 HTML（含同一张 5KB base64 logo）被复制了三份。
def tab_screening():
    view_screening.render()


def tab_resume_analysis():
    view_analysis.render()


def tab_ai_interview():
    view_interview.render(render_digital_human=render_digital_human, speak=speak_text)


def tab_report():
    view_report.render()

# ── Main ─────────────────────────────────────────────

# ── Candidate Interview Routing ──
query_params = st.query_params
if query_params.get("role") == "candidate" and query_params.get("token"):
    token = query_params["token"]
    st.session_state["candidate_token"] = token
    page_candidate()
    st.stop()

render_sidebar()
render_audio_player()
# ── 顶部品牌条 ────────────────────────────────────────
# ★ 改之前这里是一行居中的 13px 灰色小字，而下面每个模块的标题是 28px 大字 ——
#   **信息层级是倒置的**：应用名比它下属的模块名还弱。
#   现在品牌条承担"我是谁"，模块头承担"我在哪一步"，各司其职。
from app.i18n import t as _t, get_lang as _get_lang

st.markdown(f"""
<div class="brand-bar">
    <div class="brand-left">
        <span class="brand-mark">AI</span>
        <span class="brand-name">{_t('app.name')}</span>
    </div>
    <div class="brand-flow">
        <span class="flow-step">{_t('nav.analysis')}</span><span class="flow-arrow">→</span>
        <span class="flow-step">{_t('nav.interview')}</span><span class="flow-arrow">→</span>
        <span class="flow-step">{_t('nav.report')}</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ★ 仍用 st.radio 而不是 st.tabs —— 这是**功能决定的，不是偷懒**：
#   st.tabs() 无法用代码切换，而「查看评估报告」等按钮需要跳转到别的页
#   （见 tab_ai_interview 里对 active_tab 的赋值）。radio 是唯一能同时满足
#   "可点击"和"可编程切换"的原生组件。
#   问题从来不是选错了组件，而是它**长得像单选框**。下面的 CSS 把它变成分段控件。
# ★ 导航项用「稳定 key + 显示名分离」：
#   key 是内部标识（不随语言变），label 才是翻译后的显示文案。
#   之前把中文标签本身当状态存进 session_state，一旦切成英文，
#   `active_tab` 里存的旧中文标签就再也匹配不上任何选项 —— 切语言会把
#   用户踢回首页。分离之后，语言和导航状态互不影响。
NAV = [
    # ★ MVP 主链路入口：A 的简历筛选模块（已完成）
    ("screening", "📋 简历筛选"),
    ("risk", "⚡ 智能分析"),
    ("interview_eval", "📝 面试评价"),
    # ── 基座原有页面（analysis/interview/report/skills）：MVP 阶段隐藏，
    #    避免 demo 暴露未完成的基座能力；B/C 模块完成后在此追加各自入口 ──
    # ("analysis",  "📄 " + _t("nav.analysis")),
    # ("interview", "🤖 " + _t("nav.interview")),
    # ("report",    "📊 " + _t("nav.report")),
    # ("skills",    "🧩 " + _t("nav.skills")),
    ("settings",  "⚙️ " + _t("nav.settings")),
]
nav_keys = [k for k, _ in NAV]
nav_labels = {k: v for k, v in NAV}

_cur = st.session_state.get("active_tab", "screening")
if _cur not in nav_keys:                    # 隐藏基座页后，所有旧标签统一回退到 screening
    _cur = "screening"

active = st.radio("导航", nav_keys,
    index=nav_keys.index(_cur),
    format_func=lambda k: nav_labels[k],
    key="_nav_radio", horizontal=True, label_visibility="collapsed")
st.session_state.active_tab = active

if active == "screening":
    tab_screening()
elif active == "analysis":
    tab_resume_analysis()
elif active == "risk":
    view_risk.render()
elif active == "interview":
    tab_ai_interview()
elif active == "interview_eval":
    view_interview_eval.render()
elif active == "report":
    tab_report()
elif active == "skills":
    from app.views import skills_admin
    skills_admin.render()
elif active == "settings":
    from app.settings_page import render_settings_page
    render_settings_page()
