# 📘 Claude Code 官方使用指南

> 来源：[Anthropic Official](https://docs.anthropic.com/en/docs/claude-code)
> 最后同步：待 sync_master_factory.py 首次运行后自动填充

---

## 概述

Claude Code 是 Anthropic 推出的 AI 编程助手命令行工具，深度集成于终端环境中。

## 核心能力

- **代码生成与编辑**：直接在项目中生成、修改、重构代码
- **多文件操作**：跨文件的复杂重构和架构调整
- **Git 集成**：自动创建分支、提交、创建 PR
- **终端控制**：执行命令、管理进程、调试
- **上下文理解**：深度理解项目结构和代码库

## 快速入门

```bash
# 安装 Claude Code
npm install -g @anthropic-ai/claude-code

# 在项目目录启动
cd your-project
claude
```

## 高级技巧

- 使用 `/skill` 指令加载领域专用技能
- 通过 CLAUDE.md 文件注入项目级系统提示
- 利用 Memory 系统跨会话保持上下文

---

<!-- ⚠️ 此文件由 sync_master_factory.py 自动同步 -->
<!-- 手动编辑会被下次同步覆盖 -->
