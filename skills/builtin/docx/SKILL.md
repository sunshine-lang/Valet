---
name: docx
description: 处理 Word 文档。用户上传、查看、摘录 .docx，或要求整理成 Word 可用的文稿时使用。
metadata:
  title: Word
---

# Word

这是启动时自带的基础技能。

1. 用户上传的 `.docx` 在 `/uploads`。用 `ls` 确认路径，再用 `read_file` 读取抽出的正文。
2. 保留标题、列表和用户强调的原话。不要编造文档里没有的内容。
3. 需要交付的文稿用 `write_file` 写成 Markdown 或纯文本，放到 `/outputs`，并说明这是可供 Word 打开或粘贴的文本，不是二进制 `.docx`。
4. 读不到正文时，告诉用户文件无法解析，不要假装已经看过。
