# 轨藏 PPT 杂志风技能

## 技能标识
- **名称**: 轨藏 PPT 杂志风
- **版本**: 1.0.0
- **类型**: 演示文稿生成技能
- **输出格式**: HTML (Reveal.js)

## 概述
本技能用于生成杂志排版风格的 HTML 演示文稿（基于 Reveal.js 框架）。以"轨藏"为品牌调性，强调大图、大字、留白的杂志排版美学，适合产品发布、品牌宣讲、创意提案等场景。

## 设计原则

### 核心美学
- **杂志排版感**: 每一页都是一张独立的海报级版面
- **强对比**: 黑白色调为主，辅以高饱和强调色
- **大留白**: 内容不拥挤，呼吸感是奢侈
- **字体层次**: 标题/副标题/正文三级跳，字号差距拉开

### 色彩方案（三套可选）
| 方案 | 主色 | 强调色 | 背景 |
|------|------|--------|------|
| 暗夜模式 | #FFFFFF | #FFD700 | #0A0A0A |
| 极白模式 | #1A1A1A | #E63946 | #FAFAFA |
| 靛蓝模式 | #F5F5F5 | #00D2FF | #1B1B3A |

### 字体规则
- 标题: 72-96px, font-weight: 900
- 副标题: 28-36px, font-weight: 300, letter-spacing: 0.15em
- 正文: 18-22px, font-weight: 400, line-height: 1.8
- 优先使用系统原生字体栈: `-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif`

### 图片处理
- 全幅出血图片占整页
- 图片上方叠加半透明渐变遮罩
- 遮罩方向: 黑→透明（底部）或透明→黑（顶部）

## 页面模板

### 1. 封面页
```
┌─────────────────────────┐
│                   ····· │
│  大标题占画面 60%       │
│  副标题一行             │
│                   ····· │
│  日期 / 作者            │
└─────────────────────────┘
```

### 2. 章节过渡页
- 巨大数字序号 (200px+)
- 章节标题
- 纯色背景

### 3. 内容页（图文混排）
- 左文右图 或 上图下文
- 标题区 + 正文区 + 图片区
- 图片带圆角或剪裁

### 4. 引语页
- 巨大引号装饰
- 居中引用文字
- 出处署名

### 5. 结尾页
- Logo / 二维码
- 联系方式
- 致谢短语

## 技术实现

### Reveal.js 配置
```javascript
Reveal.initialize({
  width: 1920,
  height: 1080,
  margin: 0,
  minScale: 0.2,
  maxScale: 2.0,
  controls: false,
  progress: true,
  center: false,
  transition: 'fade',
  backgroundTransition: 'fade',
});
```

### CSS 自定义属性
```css
:root {
  --color-bg: #0A0A0A;
  --color-text: #FFFFFF;
  --color-accent: #FFD700;
  --color-muted: #888888;
  --font-display: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --font-body: 'PingFang SC', 'Microsoft YaHei', sans-serif;
  --spacing-unit: 8px;
}
```

### 自定义 Fragment 动画
- `.fade-up` — 淡入上浮
- `.slide-left` — 从左滑入
- `.scale-in` — 缩放弹入
- `.letter-spacing` — 字间距展开

## 工作流程
1. 接收用户大纲 → 分析内容结构
2. 匹配页面模板 → 确定每页版式
3. 生成 HTML 代码 → 注入内容
4. 输出完整可运行的 PPT 文件

## 输出规范
- 生成单个 `index.html` 文件
- 使用 CDN 引入 Reveal.js
- 所有样式内联于 `<style>` 标签
- 幻灯片结构置于 `<div class="reveal"><div class="slides">` 内
- 每页幻灯片使用 `<section>` 标签

## 示例大纲格式
```
标题: 产品发布会
章节1: 市场洞察 → 数据页 + 引语页
章节2: 产品亮点 → 3个亮点各1页
章节3: 技术架构 → 架构图 + 技术指标
结尾: 联系方式 + 致谢
```

---

> 💡 **提示**: 将以上内容作为系统上下文注入后，AI 将按照本技能定义的规则生成符合"轨藏杂志风"的 Reveal.js PPT。
