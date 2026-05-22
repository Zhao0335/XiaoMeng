---
name: compute-pro
description: 用 Python + numpy/scipy/sympy 执行数学计算和科学计算
version: 1.0.0
emoji: 🔢
always: false
risk: sensitive
min_user_level: admin
min_model_tier: cloud
tags:
  - math
  - python
  - compute
  - science
---

# 科学计算技能

通过 `run_command` 调用 Python 执行数学计算任务。

## 可用库

- `numpy` — 数值计算、矩阵运算
- `scipy` — 科学计算、积分、优化
- `sympy` — 符号计算、微积分、方程求解
- `mpmath` — 高精度数学运算

## 使用模板

```bash
python3 -c "
import numpy as np
import sympy as sp
from scipy import integrate, optimize
print(result)
"
```

多行计算用 heredoc：

```bash
python3 << 'EOF'
import numpy as np
x = np.array([1, 2, 3])
print(x.mean())
EOF
```

## 常用场景

### 数值计算
```python
import numpy as np
A = np.array([[3, 2], [1, 2]])
b = np.array([7, 5])
x = np.linalg.solve(A, b)
print(x)
```

### 符号计算
```python
import sympy as sp
x = sp.Symbol('x')
f = sp.sin(x) * sp.exp(x)
print(sp.integrate(f, (x, 0, sp.pi)))
```

### 求导
```python
import sympy as sp
x = sp.Symbol('x')
print(sp.diff(x**3 + 2*x**2 + 1, x))
```

## 注意

- 复杂计算用 heredoc（避免引号嵌套问题）
- 用 print() 输出结果
- 需要安装新库时先确认主人同意
