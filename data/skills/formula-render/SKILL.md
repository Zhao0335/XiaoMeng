---
name: formula-render
description: 将数学公式渲染为图片自动发送——在回复中用 $$...$$ 包裹 LaTeX 公式即可触发
version: 1.0.0
emoji: 📐
always: true
risk: read_only
min_user_level: stranger
min_model_tier: local
tags:
  - math
  - formula
  - latex
  - image
---

# 数学公式渲染技能

你的回复中可以包含 LaTeX 数学公式。系统会自动将公式渲染为图片并作为额外消息发送，无需你手动操作。

## 使用方法

用双美元符号 `$$...$$` 包裹 LaTeX 公式：

- 普通文字正常写，把公式部分用 `$$...$$` 括起来
- 系统发送时，文字中的 `$$...$$` 会替换为 `[见下方公式图]`，然后紧接着发送公式图片

## 语法示例

| 数学表达           | 写法                                      |
|--------------------|-------------------------------------------|
| 爱因斯坦质能方程   | `$$E = mc^2$$`                            |
| 分数               | `$$\frac{a}{b}$$`                         |
| 求和               | `$$\sum_{i=1}^{n} x_i$$`                 |
| 定积分             | `$$\int_0^1 f(x)\,dx$$`                  |
| 极限               | `$$\lim_{x \to 0} \frac{\sin x}{x} = 1$$` |
| 矩阵               | `$$\begin{pmatrix} a & b \\ c & d \end{pmatrix}$$` |
| 二次公式           | `$$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$$` |
| 多行推导/连等式    | `$$\begin{aligned} f(x) &= \cdots \\ &= \cdots \end{aligned}$$` |

## ⚠️ 多行公式必须放进一个 `$$` 块

每个 `$$...$$` 渲染成一张独立图片。**不要**把一个推导过程拆成多个 `$$`。

❌ 错误（产生 3 张图片）：

```
$$f(x) = a^2 + b^2$$
$$= (a+b)^2 - 2ab$$
$$= c^2$$
```

✅ 正确（1 张图片，对齐整洁）：

```
$$\begin{aligned}
f(x) &= a^2 + b^2 \\
     &= (a+b)^2 - 2ab \\
     &= c^2
\end{aligned}$$
```

分步推导、连等式、联立方程组、积分过程——都放进一个 `$$\begin{aligned}...\end{aligned}$$` 或 `$$\begin{cases}...\end{cases}$$`。

## 何时使用

- 用户请求推导或展示数学公式
- 回复涉及物理、工程、统计等包含公式的场景
- 用户说"用公式写出来"、"推导一下"、"LaTeX 格式"

## 注意

- 真正相互独立的不同公式才分开用多个 `$$...$$`
- 渲染使用完整系统 LaTeX + amsmath，支持 `aligned`、`cases`、`pmatrix`、`bmatrix` 等所有环境
- 极复杂的环境（TikZ、pgfplots）不支持
