# Changelog

All notable changes to the AI Intelligent Recruitment System will be documented in this file.

## [2.0.0] — 2026-07-01

### Added
- **Project Merge**: Combined AI-Interview Agent and AIOffer-Research into a single unified system
- **Interview Link Generation**: One-click generation of unique candidate interview links (`?role=candidate&token=xxx`), shareable with 48h expiry
- **Candidate Self-Service Page**: Standalone interview page for candidates with no sidebar/settings, full LLM-driven interview flow
- **Voice Input**: Browser-native Web Speech API integration for candidate speech-to-text input with real-time feedback
- **TTS Multi-Engine Fallback**: Three-tier TTS chain (edge-tts → Xunfei WebSocket → XTTS offline DLL) for zero-cost voice synthesis
- **Virtual Digital Human**: Professional SVG-based half-body avatar with CSS breathing + blink animation and JS mouth sync
- **PDF OCR Fallback**: Added pdfplumber as secondary parser, with optional rapidocr-onnxruntime for scanned PDFs
- **Professional UI Redesign**: Glassmorphism cards, score gradient bars, step indicators, feature stat cards across all tabs
- **Comprehensive README**: 11 documented technical challenges with solutions, architecture diagrams, and data flow

### Changed
- **Tab Navigation**: Migrated from `st.tabs` to `st.radio` + session_state for programmatic switching
- **Interview Termination**: Removed early termination by pending_dimensions; now only max_rounds governs interview length
- **Performance**: Removed 4 duplicated ~14KB base64 images, reduced animation FPS from 60 to 15

### Fixed
- **Tab Jump Bug**: Buttons in Resume Analysis and Interview tabs now correctly navigate to target tabs
- **st.session_state Binding Conflict**: Resolved Streamlit widget key binding issue preventing programmatic tab switching
- **Question Count Mismatch**: Interview now consistently runs to configured question count (previously terminated early)

## [1.0.0] — 2026-06-28

### Added
- **Resume Analysis Tab**: JD + Resume multi-format parsing (PDF/DOCX/TXT), match scoring, fuzzy Q&A
- **Question Generation**: LLM-powered stratified question sampling across 5+ evaluation dimensions
- **AI Interview Tab**: Role-playing interviewer with persona generation, multi-turn dialogue, dimension-by-dimension evaluation
- **Assessment Report Tab**: 5-dimensional radar chart, per-question review, hiring recommendation with evidence
- **Multi-Provider LLM Support**: DeepSeek / Qwen / OpenAI / Kimi via unified OpenAI-compatible API
