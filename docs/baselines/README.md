# 本地版本基线

`baseline-20261010-before-onejev` 固定 OneJev 接入前的源码、配置、任务、报告和审批计划。基线离线测试 103 项通过。

约 39 GB 的 runs、后续模型权重/独立环境、缓存和密钥文件不进入 Git，原文件留在本机；对应 metadata、summary、steps 的 SHA256 见本目录清单。Git 仓库没有远程地址。

提交身份仅配置在此仓库：guiyuanze <guiyuanze@localhost>。开发分支为 feature/onejev-local；查看基线可使用 git show baseline-20261010-before-onejev:run.py，无需覆盖当前目录。
