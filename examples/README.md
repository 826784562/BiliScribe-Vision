# 原创示例与复现

示例全部自制，不含真实 B 站课程、课本或用户资料。BV1234567890/CID 123 是测试身份，不能拿去下载。本目录用来说明输出质量与离线接口，不代表真实课程基准。

## 文字示例

输入：[课程清单](text/course_manifest.json)、[SRT](text/transcript.srt)。输出片段：[讲义](text/讲义.md)。保留“以前考过”的条件，不升级成“必考”；缺题干与答案时明确缺失。

准备与导入命令见 [快速开始](../docs/quickstart.md)。理解结果必须由当前 Codex 阅读实际 packet 后填写，不能用测试夹具假装模型推理。

## 画面示例

自制 Data Lab 导出场景包含菜单、参数和结果三屏。图片由离线测试生成，已由当前 Codex 实际读取。

- [入口](vision/01-menu.png)
- [参数](vision/02-settings.png)
- [结果](vision/03-result.png)
- [对应转录](vision/transcript.md)
- [可执行步骤与缺失](vision/讲义.md)

这里的文件名 lesson.csv、CSV 和逗号分隔符来自画面，不能只靠“照图上填”的转录猜出。未提供真实软件和版本，未验证实机操作；讲义明确说明此限制。

使用虚拟环境执行 scripts/test_pipeline.py --demo .cache/vision-demo 可生成 12 秒合成视频与材料包；随后让当前 Codex 阅读 packet 并实际打开图片。不要把生成器当理解模型。
