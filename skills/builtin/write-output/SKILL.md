---
name: write-output
description: 用户需要可下载的结果、报告或整理后的文件时使用。把要交付的内容写到 /outputs，不要只在对话里贴大段原文。
---

1. 把要交给用户的结果用 `write_file` 写到 `/outputs`。
2. 覆盖已有文件前必须先 `read_file`。
3. 对话里说明写了哪个路径，不要只贴大段原文。
