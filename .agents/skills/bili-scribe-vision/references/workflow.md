# 执行命令示例

在项目根目录运行，Python 使用 .venv 中的解释器；以下命令是供执行 Skill 的 Codex 使用的步骤，不是独立模型推理程序。

1. bili_fetch.py manifest BV... -o outputs/course/course_manifest.json
2. 用户确认范围后保存 selection=confirmed/excluded 和 study_order。
3. bili_fetch.py subs outputs/course/course_manifest.json -o transcripts
4. 无字幕时：bili_fetch.py audio <manifest> -o downloads，再 transcribe.py downloads --manifest <manifest> -o transcripts
5. 仅画面模式：bili_fetch.py video <manifest> -o downloads
6. video_visual.py --video <该讲视频> --lesson-id L001 -o .cache/bili-scribe/course/L001-visual.json
7. evidence.py prepare --manifest <manifest> --transcripts transcripts --mode transcript-images --visual-manifest <各讲visual.json...> -o .cache/bili-scribe/course/evidence_manifest.json
8. 当前 Codex 读 packets/*.md 并实际打开对应图片，共同理解后写每个 analysis JSON。
9. evidence.py record --evidence <evidence_manifest> --analysis <analysis.json> -o outputs/course/understanding_manifest.json
10. evidence.py check --evidence <evidence_manifest> --understanding <understanding_manifest>
11. materials.py <PPT/PDF等> -o outputs/course/课件笔记 --extract-images
12. 课本：materials.py <课本.pdf> --textbook --manifest-output outputs/course/textbook_manifest.json；先展示章节，再按用户范围运行 --select。已确认印刷页映射时传 --book-page-offset。按选中章节的物理页范围使用 materials.py <课本.pdf> --pages <选中页范围> -o outputs/course/课件笔记/课本补充 提取文字，按需 --render-pages 读取图像；不要直接对整本课本提取正文。
13. 当前 Codex 将视频理解与材料融合，写讲义、大纲、术语、独立习题及报告；逐步走查操作复现。
14. validate_course.py outputs/course --report outputs/course/validation_report.json

仅文字模式跳过 5–6，并在 7 中使用 --mode transcript-only，不传 --visual-manifest。PPT/PDF 的融合仍可进行。

## 统一身份

course_manifest 的 units 字段含 lesson_id/bvid/cid/page/title/duration/source_type/source_order/study_order/selection/added_by。lesson_id 唯一，BVID/CID 配对唯一；多个分 P 共享 BVID 是正常情况。selected 的 study_order 唯一且与 source_order 分开。

字幕和 ASR 都输出同样的稳定文件名前缀与 JSON identity，不能按标题猜配对。已有 MD/SRT/TXT 用：

evidence.py import-transcript --manifest <manifest> --lesson-id L001 --input <转录文件> -o transcripts

无时间文字在已知 duration 时保存为全讲 coarse 块；每个材料包仍可读取这份文字，但不得给口述推断精确时间。讲义中的相关引用注明“粗略时间 / 全讲转录”。

## 已有图片输入

已有截图不必重新下载视频。先确认讲次、每张截图所属时间及教学状态，写候选 JSON；frame_path 相对该 JSON 文件解析。例：

    {"segments": [{
      "lesson_id": "L001", "segment_id": "VS0001", "start": 0, "end": 30,
      "boundary_source": "user-windows",
      "candidates": [{"timestamp": 12, "frame_path": "screenshots/export.png",
                      "stable": true, "completed": true, "completeness": 1}]
    }]}

    video_visual.py --segments-json <候选JSON> -o <visual_manifest.json>

示例 completed=true 只在确认该图为该教学状态的完成态时使用；不要将任意图片标完成。状态范围应连续覆盖所选讲次，复杂操作拆多个状态。截图不足时补充素材或如实报告；未知时间和对应关系要先核对，不能按文件名猜测。

原始语音路径不影响文字+图像理解；有字幕就无需为了“听原始音频”再下载音频。

## 资料视觉

materials.py <课本或课件.pdf> --render-pages 5,8-10 --image-dir .cache/bili-scribe/course/material_pages

先确认所选课本范围，再渲染其中需要看图的页面。PPT --extract-images 提取的图片带幻灯片号，不替代整个幻灯片布局；复杂 PPT 用可用工具渲染，或接受用户提供的 PDF 版。

## 续跑

原媒体可按稳定身份复用。准备包/理解记录用 mode + 内容指纹关联；转录或帧变了必须重建包并重新理解受影响状态。已有仅文字讲义切成画面模式时，重新理解并撰写，不能只补图片标签。保存缺失与 incomplete，不把没读的状态算完成。
