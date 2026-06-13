# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is an Obsidian vault. The `.obsidian/` directory contains Obsidian workspace configuration.

## Current Project

The user intends to build a **web-based PPT (slides)** using **Reveal.js** within this vault. Content topic and style are yet to be determined.

## Git

- Remote: `origin` → `https://github.com/yanyan-oss/ClaudeSandbox` (private)
- Branch: `main`
- `.gitignore` 精准屏蔽：外部克隆项目、超大文件、个人配置、`secrets.txt`
- 自动化同步：`sync_master_factory.py` 全自动 pull/push 闭环

## Key Scripts

| 脚本 | 功能 |
|------|------|
| `sync_master_factory.py` | 全自动同步工厂：Git 防御 → 指南覆盖 → 沉淀抓取 → 隐私保护 → 一键推送 |
| `super_save_workflow.py` | 小鹅通直播回放全自动处理管道（ASR + LLM） |
| `skill-manager.js` | 技能调度核心 |

## Obsidian

- Vault root: `E:\ClaudeSandbox\ClaudeSandbox\`
- Standard Obsidian conventions apply: Markdown notes, `[[wikilinks]]` for internal linking
- The `泡泡堂/` folder exists as a potential project workspace
