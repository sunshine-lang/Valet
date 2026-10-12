---
name: read-uploads
description: 用户上传了文件，或要基于附件回答时使用。先查看 /uploads，再读取需要的文件，不要编造文件里没有的内容。
---

1. 用 `ls` 查看 `/uploads`。
2. 需要内容时用 `read_file`，路径使用 `ls` 给出的虚拟路径。
3. 不要编造文件里没有的内容。读不到就告诉用户。
