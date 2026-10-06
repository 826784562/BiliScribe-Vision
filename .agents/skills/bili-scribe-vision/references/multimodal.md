# 当前 Codex 的文字与图像理解接口

这份 Skill 使用执行者的当前会话模型。Python 文件接口准备对齐材料并记录理解，图片经当前图片工具（通常 view_image）真实进入会话上下文。脚本不负责推理，不启用新模型/API，也不调用另一个 Codex。

## 顺序

转录与画面预处理 → packet 的文字 + 实际图像读取 → 视频理解记录 → PPT/PDF 资料融合 → 第一份最终讲义 → 来源与复现审计。

仅文字模式不读取视频画面。两个模式都未直接听取原始音频。

## 材料包

evidence.py prepare 为每个时间窗生成 packet MD 和 evidence_manifest.json：

- packet_id、lesson_id、bvid、cid、start/end、mode。
- 原转录的句/块 ID、起止时间、正文和 timing=segment/coarse。
- 图像的 frame_id、角色、时间、绝对路径与 SHA-256。
- 输入指纹与待核对事项。

读文字后逐一打开图片；别把路径文字或成功选帧当成读图。当前接口不返回可由本项目独立认证的会话模型 ID 时，用 current-session，如有可靠值再写真实型号，不猜型号。

## 理解结果格式

每个 packet 写一个 analysis JSON。视频理解阶段只收 COURSE_SPOKEN 和 COURSE_VISUAL；PPT 与课本在之后融合。示例字段（内容需替换为真实证据）：

{
  "packet_id": "L001-VS0001",
  "mode": "transcript-images",
  "status": "complete",
  "summary": "本教学状态的实际内容",
  "reviewed_frame_ids": ["L001-VS0001-F1"],
  "entries": [
    {
      "entry_id": "L001-VS0001-E1",
      "kind": "concept",
      "text": "老师表达的内容，保留条件与确定性。",
      "provenance": "COURSE_SPOKEN",
      "timestamp": 5.0,
      "transcript_ids": ["T00001"],
      "frame_ids": [],
      "quote": "对应转录中的逐字片段"
    },
    {
      "entry_id": "L001-VS0001-E2",
      "kind": "visual_state",
      "text": "画面中可以看到的具体控件和状态。",
      "provenance": "COURSE_VISUAL",
      "timestamp": 8.0,
      "transcript_ids": [],
      "frame_ids": ["L001-VS0001-F1"]
    }
  ],
  "operations": [],
  "contradictions": [],
  "gaps": []
}

仅文字模式的 reviewed_frame_ids 与 frame_ids 都为空，不得有 COURSE_VISUAL。口述引用要有实际转录原文；这是转录支持，不是重新听音频认证。画面条目时间必须对应支持图片。所有时间属于原讲次。无时间的文字可以导入为全讲 coarse 块（需已知讲次时长），只表示属于该讲，不能生成精确口述时间；输出注明粗略时间。操作条目 kind=operation 必须另有 operations 步骤记录。

status=incomplete 用于无法充分读取的状态；仍应保存已知结论、gaps 和矛盾。complete 只表示该材料包已完成理解，不保证操作可以复现；操作的 reproducible 与 missing 单独记录。

## 操作记录

operations 中每项记录：

{
  "title": "操作目标",
  "prerequisites": ["已确认的起始界面、已有文件/对象、必要版本或设置"],
  "reproducible": true,
  "missing": [],
  "steps": [
    {
      "location": "菜单路径或窗口/面板中的具体控件",
      "action": "点击、选择、输入、运行等",
      "input": "完整值与单位；无输入写无",
      "expected_result": "应出现的界面状态、数值、图形或文件",
      "check": "如何确认此步成功；有证据时注明常见失败",
      "entry_ids": ["L001-VS0001-E2"]
    }
  ]
}

只有证据支持且关键位置/参数/结果都齐全时才设 reproducible=true。缺图、短暂菜单、未知参数要精确请求补帧/操作时间窗，或写 missing 与 false。复杂操作跨多个 packet 时，最终讲义按连续动作顺序整合；不能以“结果截图存在”推断所有中间步骤齐全。

## 保存、重跑与审计

evidence.py record 检查 ID、模式、支持原话、来源、时间及操作字段后，保存理解记录。check 对比输入指纹和覆盖；换模式或换证据需重新理解。

image_read_evidence=executing-agent-declaration 表示执行 Codex 声明实际看过图片，不能当作独立工具调用证明。最终验收还需对照实际图片抽查；未运行软件时只能报告证据核对与文档走查，不报告实机复现。

处理图像失败时保留 incomplete，并报告缺失，不默认退回仅文字。已选择仅文字时照常处理，报告画面中才有的信息没有验证。
