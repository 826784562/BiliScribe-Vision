# BiliScribe-Vision

[中文](README.md) · [Quick start](docs/quickstart.md) · [Examples](examples/README.md)

Turn synchronized video frames and transcripts into study notes with actionable, evidence-backed walkthroughs.

This is a Codex Skill with local preparation tools. The **Codex model executing the skill** understands the evidence and writes the notes. Python does not call the running conversation model or independently produce a course. Image understanding requires an actual image-reading tool in that conversation; image paths alone are insufficient.

## Install

Python 3.11+ (3.12 recommended), Git and Codex are required.

```bash
git clone https://github.com/826784562/BiliScribe-Vision.git
cd BiliScribe-Vision
python install.py
```

The installer copies a self-contained skill to CODEX_HOME/skills (default ~/.codex/skills). It does not download dependencies or models. It stops if the destination exists; --update explicitly updates source files and preserves local .env/.venv. Open a new Codex conversation and ask:

> Use $bili-scribe-vision. Inspect and set up the local dependencies. Confirm the lessons in this course: <URL>. Understand the transcript together with actual key frames, then combine my slides and selected textbook chapters into notes. Preserve citations and label missing evidence and independent AI explanations. Write interface locations, parameter values, actions, expected results and checks for each operation.

Or open this repository in Codex and use the project skill under .agents/skills/bili-scribe-vision. See the bilingual commands in [quick start](docs/quickstart.md). Local ASR is optional: add --with-asr when setting up dependencies.

## Outputs and evidence

Lesson notes, a course outline, glossary, separate exercise explanations and a delivery report are stored under outputs/<course-id>/. Stable lesson identities and understanding records retain source references. Textbooks require chapter selection and a confirmed printed/PDF page mapping. Course speech, video visuals, slides, textbook supplements and AI explanations remain distinct.

Both editions understand spoken content through subtitles/transcripts, **not direct raw-audio input**. Codex processing follows the account's own service and billing arrangement. Optional cloud ASR/OCR uploads only the selected material after user authorization; local ASR may download model weights on first use. Media, real transcripts, textbooks, caches and secrets are excluded from distribution.

## Limits and verification

Frame proposals are heuristic. Brief menus, cursor actions and same-slide parameter changes may require additional targeted frames. Extracted PPTX images do not preserve full slide layout; export to PDF when necessary. Automatic validation checks identities, citations, coverage and stale inputs; it cannot certify semantic accuracy or actual software execution. Examples are original synthetic scenes, not real course benchmarks. Network/ASR compatibility still needs live, authorized testing.

## Contribute

See [CONTRIBUTING](CONTRIBUTING.md), [security guidance](SECURITY.md) and [roadmap](docs/roadmap.md). Use anonymized, redistributable reproductions. CI is configured for Windows and Ubuntu on Python 3.11/3.12; its remote success is not claimed until it runs.

GPL-3.0-or-later. Original copyright and third-party attribution are preserved in [LICENSE](LICENSE) and [NOTICE](NOTICE). Derived from the v12 visual-understanding work. See the companion [BiliScribe-Audio](https://github.com/826784562/BiliScribe-Audio).
