#!/usr/bin/env node
/**
 * skill-manager.js — GitHub 技能管理 · 命令行选单
 *
 * 运行: node skill-manager.js
 *
 * 功能:
 *   ● 精美黑色框框选单，键盘 ↑↓ 导航
 *   ● 轨藏 PPT 杂志风技能 → 加载 SKILL.md → 自动对话模式
 *   ● 默认 Reveal.js 基础模版
 */

import { select } from '@inquirer/prompts';
import chalk from 'chalk';
import ora from 'ora';
import boxen from 'boxen';
import fs from 'fs';
import path from 'path';
import readline from 'readline';
import { fileURLToPath } from 'url';

// ── 路径 ──────────────────────────────────────
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILL_PATH = path.join(__dirname, 'SKILL.md');

// ── 工具 ──────────────────────────────────────
const clear = () => console.clear();

// ── 头部 Banner ───────────────────────────────
function drawHeader() {
  const title = chalk.bold.cyan('✦  SKILL MANAGER  ✦');
  const subtitle = chalk.dim('GitHub 技能管理 · 命令行选单');
  console.log(
    boxen(`${title}\n\n${subtitle}`, {
      borderStyle: { topLeft: '╭', topRight: '╮', bottomLeft: '╰', bottomRight: '╯',
                     top: '─', bottom: '─', left: '│', right: '│' },
      borderColor: 'cyan',
      padding: { top: 1, bottom: 1, left: 4, right: 4 },
      margin: { top: 1, bottom: 1 },
    })
  );
}

// ── 闪烁点点点加载动画 ────────────────────────
async function dotsAnimation() {
  console.log(chalk.dim('\n  ⚡ 正在挂载系统上下文...'));

  const spinner = ora({
    text: chalk.white('加载 SKILL.md'),
    spinner: {
      interval: 80,
      frames: [
        '●○○○○', '○●○○○', '○●●○○', '○○●○●',
        '●●●○○', '○●○●○', '●○●○●', '●●●●○',
        '●●●●●', '●○●○○', '○●○●○', '●●○●●',
        '○○●○○', '●○●○●', '○○○●○', '●●●●●',
      ],
    },
    color: 'cyan',
  }).start();

  await new Promise((r) => setTimeout(r, 2200));

  spinner.succeed(chalk.green('上下文挂载完成！'));
  console.log('');
}

// ── 主选单 ────────────────────────────────────
async function showMenu() {
  clear();
  drawHeader();

  const answer = await select({
    message: '请选择一个技能',
    choices: [
      {
        name: chalk.bold('轨藏 PPT 杂志风技能') + chalk.dim('  · 绑定 SKILL.md'),
        value: 'magazine',
        description:
          chalk.dim('  ↳ ') +
          chalk.cyan('加载 SKILL.md 作为系统上下文') +
          chalk.dim(' → 全自动对话模式'),
      },
      {
        name: chalk.white('默认 Reveal.js 基础模版'),
        value: 'default',
        description:
          chalk.dim('  ↳ ') +
          chalk.white('使用 Reveal.js 标准 HTML 模板快速起步'),
      },
    ],
    theme: {
      icon: { cursor: chalk.green.bold('●') },
      style: {
        answer: (text) => chalk.green.bold(text),
        message: (text) => chalk.white.bold(text),
        error: (text) => chalk.red(text),
        helpTip: (text) => chalk.dim(text),
      },
    },
  });

  return answer;
}

// ── 加载 SKILL.md ─────────────────────────────
function loadSkillFile() {
  if (!fs.existsSync(SKILL_PATH)) {
    console.log(chalk.yellow('  ⚠ SKILL.md 不存在，正在创建默认模板...'));
    const defaultSkill =
      '# 轨藏 PPT 杂志风技能\n\n> 默认技能模板 — 请通过对话丰富此文件内容。\n';
    fs.writeFileSync(SKILL_PATH, defaultSkill, 'utf-8');
    console.log(chalk.green('  ✅ 默认 SKILL.md 已创建'));
  }
  return fs.readFileSync(SKILL_PATH, 'utf-8');
}

function displayContext(content) {
  const maxShow = 600;
  const preview =
    content.length > maxShow
      ? content.slice(0, maxShow) +
        '\n\n  …' +
        chalk.dim(` (共 ${content.length} 字符，已截断预览)`)
      : content;

  console.log(
    boxen(chalk.white(preview), {
      title: chalk.bold.green(' 📋 系统上下文已加载 '),
      titleAlignment: 'center',
      borderStyle: 'round',
      borderColor: 'green',
      padding: { top: 1, bottom: 1, left: 3, right: 3 },
      margin: { top: 1, bottom: 1 },
    })
  );
}

// ── 全自动对话模式（多行大纲输入）─────────────
async function dialogueMode() {
  console.log(
    chalk.cyan('\n  🤖 ') +
      chalk.bold.white('系统 > ') +
      chalk.white('请告诉我你的 PPT 大纲：')
  );
  console.log(chalk.dim('     逐行输入内容，单独一个空行 + 回车结束输入\n'));

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: true,
  });

  const lines = [];

  return new Promise((resolve) => {
    console.log(
      chalk.dim('  ┌─ 大纲输入 ─' + '─'.repeat(40) + '┐')
    );

    let idx = 1;
    const ask = () => {
      rl.question(
        chalk.green('  │ ') + chalk.dim(String(idx).padStart(2, '0') + '  '),
        (line) => {
          if (line.trim() === '') {
            if (lines.length > 0) {
              console.log(
                chalk.dim('  └' + '─'.repeat(48) + '┘')
              );
              rl.close();
              return;
            }
            // 第一行就空 → 重新问
            ask();
            return;
          }
          lines.push(line);
          idx++;
          ask();
        }
      );
    };

    ask();

    rl.on('close', () => {
      resolve(lines.join('\n'));
    });
  });
}

// ── 选项2：默认 Reveal.js 基础模版 ────────────
async function handleDefaultTemplate() {
  clear();
  drawHeader();

  console.log(
    boxen(
      chalk.white('将使用 ') +
        chalk.cyan.bold('Reveal.js') +
        chalk.white(' 标准配置生成演示文稿。\n\n') +
        chalk.dim('  主题: Black  |  过渡: Slide  |  比例: 16:9'),
      {
        title: chalk.bold.blue(' 📄 默认 Reveal.js 基础模版 '),
        titleAlignment: 'center',
        borderStyle: 'round',
        borderColor: 'blue',
        padding: { top: 1, bottom: 1, left: 4, right: 4 },
        margin: 1,
      }
    )
  );

  console.log(
    chalk.dim('\n  💡 提示：在后续对话中直接描述你的内容，AI 将生成标准 Reveal.js PPT。\n')
  );
}

// ── 主入口 ────────────────────────────────────
async function main() {
  process.on('SIGINT', () => {
    console.log(chalk.dim('\n\n  👋 已退出 skill-manager。\n'));
    process.exit(0);
  });

  const choice = await showMenu();

  if (choice === 'magazine') {
    clear();
    drawHeader();
    await dotsAnimation();

    const skillContent = loadSkillFile();
    displayContext(skillContent);

    const outline = await dialogueMode();

    if (outline) {
      console.log(
        boxen(chalk.white(outline), {
          title: chalk.bold.green(' ✅ 大纲已记录 '),
          titleAlignment: 'center',
          borderStyle: 'round',
          borderColor: 'green',
          padding: { top: 1, bottom: 1, left: 4, right: 4 },
          margin: { top: 2, bottom: 1 },
        })
      );
      console.log(
        chalk.green('\n  🎯 系统已就绪，可以开始生成「轨藏杂志风」PPT 了！\n') +
          chalk.dim('  ────────────────────────────────────────\n')
      );
    }
  } else if (choice === 'default') {
    await handleDefaultTemplate();
  }
}

main().catch((err) => {
  console.error(chalk.red('\n  ✖ 发生错误：'), chalk.white(err.message));
  process.exit(1);
});
