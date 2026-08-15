"""设置页：界面语言 · 模型接入 · 语音引擎状态。

════════════════════════════════════════════════════════════════
 ⚠️ 这个页面会写用户的 .env —— 首要约束是【不破坏已有配置】
════════════════════════════════════════════════════════════════

三条安全规则，每一条都对应一种会让人丢配置的写法：

 1. **逐行改写，不整体重写。** 只替换要改的那几行，其余原样保留 ——
    包括注释、空行、以及本页面根本不认识的其他变量（讯飞凭证等）。
    用 dict → 重新序列化的写法会把注释和未知项一起抹掉。

 2. **API Key 留空 = 保持不变，不是清空。** 输入框永远不回填真实 Key
    （回填就等于把密钥打印到 DOM 里），所以"空"必须解释成"没改"。
    若把空当成"清空"，用户只要打开这个页面点一次保存就会丢 Key。

 3. **先备份再写。** 写入前把原文件复制成 .env.bak，出问题能还原。

★ 另外：任何时候都不把 Key 的明文显示出来，只显示掩码与来源。
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import streamlit as st

from .config import settings
from .i18n import LANGUAGES, get_lang, set_lang, t

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# 常见服务商预设 —— 省去手填 base_url 的记忆负担
PROVIDER_PRESETS = {
    "DeepSeek":            ("https://api.deepseek.com/v1", "deepseek-chat"),
    "阿里云百炼 (Qwen)":    ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    "Moonshot (Kimi)":     ("https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    "OpenAI":              ("https://api.openai.com/v1", "gpt-4o-mini"),
    "智谱 GLM":            ("https://open.bigmodel.cn/api/paas/v4", "glm-4-plus"),
    "自定义":              ("", ""),
}


def _mask(secret: str) -> str:
    """掩码显示。★ 永远不返回明文 —— 页面上不该出现完整 Key。"""
    if not secret:
        return ""
    if len(secret) <= 10:
        return secret[:2] + "***"
    return f"{secret[:6]}…{secret[-4:]}（{len(secret)} 位）"


def _update_env(updates: dict[str, str]) -> tuple[bool, str]:
    """把 updates 写进 .env，**逐行替换，保留其余一切**。

    返回 (成功?, 说明)。
    """
    try:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=True) if ENV_PATH.exists() else []
        if ENV_PATH.exists():
            shutil.copy2(ENV_PATH, ENV_PATH.with_suffix(".env.bak"))

        remaining = dict(updates)
        out: list[str] = []
        for line in lines:
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
            key = m.group(1) if m else None
            if key and key in remaining:
                out.append(f"{key}={remaining.pop(key)}\n")
            else:
                out.append(line)          # 注释、空行、未知变量 —— 原样保留

        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        for key, val in remaining.items():  # 原本不存在的键，追加
            out.append(f"{key}={val}\n")

        ENV_PATH.write_text("".join(out), encoding="utf-8")
        return True, str(ENV_PATH)
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"


def _test_connection(base_url: str, model: str, api_key: str) -> tuple[bool, str]:
    """发一次最小请求验证配置。★ 不用当前进程的 settings，用表单里的值 ——
    否则测的是旧配置，绿灯与你刚填的内容无关。"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=20)
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        got = (r.choices[0].message.content or "").strip()
        return True, f"{model} → {got[:40] or '(空响应)'}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:160]}"


def render_settings_page() -> None:
    st.markdown(
        f"""<div class="app-header">
            <h1>⚙️ {t('settings.title')}</h1>
            <p>{t('settings.subtitle')}</p>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── 语言 ────────────────────────────────────
    st.markdown(f"##### 🌐 {t('settings.language')}")
    codes = list(LANGUAGES)
    picked = st.radio(
        t("settings.language"),
        codes,
        index=codes.index(get_lang()),
        format_func=lambda c: LANGUAGES[c],
        horizontal=True,
        label_visibility="collapsed",
        key="_lang_radio",
    )
    if picked != get_lang():
        set_lang(picked)
        st.rerun()

    st.divider()

    # ── 模型接入 ────────────────────────────────
    st.markdown(f"##### 🧠 {t('settings.model')}")

    has_key = bool(settings.LLM_API_KEY)
    st.caption(
        f"{t('settings.current')}：`{settings.LLM_MODEL}` @ `{settings.LLM_BASE_URL}` · "
        f"API Key {t('settings.key_kept') if has_key else t('settings.key_empty')}"
        + (f" `{_mask(settings.LLM_API_KEY)}`" if has_key else "")
    )

    names = list(PROVIDER_PRESETS)
    cur_preset = next(
        (n for n, (u, _) in PROVIDER_PRESETS.items() if u and u == settings.LLM_BASE_URL),
        "自定义",
    )
    c1, c2 = st.columns([1, 2])
    with c1:
        preset = st.selectbox(t("settings.provider"), names, index=names.index(cur_preset))
    preset_url, preset_model = PROVIDER_PRESETS[preset]

    with c2:
        base_url = st.text_input(
            t("settings.base_url"),
            value=preset_url if (preset != cur_preset and preset_url) else settings.LLM_BASE_URL,
        )

    c3, c4 = st.columns(2)
    with c3:
        model_name = st.text_input(
            t("settings.model_name"),
            value=preset_model if (preset != cur_preset and preset_model) else settings.LLM_MODEL,
        )
    with c4:
        # ★ 永远不回填真实 Key。空 = 不改动。
        api_key_in = st.text_input(
            t("settings.api_key"),
            value="",
            type="password",
            placeholder=_mask(settings.LLM_API_KEY) if has_key else "sk-...",
            help=t("settings.key_help"),
        )

    b1, b2, _ = st.columns([1, 1, 2])
    with b1:
        if st.button(f"🔌 {t('settings.test')}", use_container_width=True):
            key_for_test = api_key_in or settings.LLM_API_KEY
            if not key_for_test:
                st.error(t("settings.key_empty"))
            else:
                with st.spinner(""):
                    ok, detail = _test_connection(base_url, model_name, key_for_test)
                (st.success if ok else st.error)(
                    f"{t('settings.test_ok') if ok else t('settings.test_fail')} — {detail}"
                )
    with b2:
        if st.button(f"💾 {t('settings.save')}", type="primary", use_container_width=True):
            updates = {"LLM_BASE_URL": base_url, "LLM_MODEL": model_name}
            if api_key_in:                      # ★ 只有真填了才动 Key
                updates["LLM_API_KEY"] = api_key_in
            ok, info = _update_env(updates)
            if ok:
                st.success(f"{t('settings.saved')}（{info}）")
                if not api_key_in and has_key:
                    st.caption("ℹ️ API Key 未改动，仍为原值")
            else:
                st.error(info)

    st.divider()

    # ── 语音引擎（只读状态）────────────────────
    st.markdown(f"##### 🔊 {t('settings.speech')}")
    from .tts_utils import engine_status
    for name, ok, why in engine_status():
        if ok:
            st.markdown(f"- **{name}** — :green[{t('settings.engine_ok')}]")
        else:
            st.markdown(f"- **{name}** — :red[{t('settings.engine_no')}]　:gray[{why}]")
