# Compute Pro 计算技能 v1.0

## 能力概述
使用 Python + numpy + scipy + sympy 进行数学计算和代码执行。
通过 `run_command` 调用 Python 执行计算任务。

## 可用库
- `numpy` (2.2.6) — 数值计算、矩阵运算
- `scipy` (1.8.0) — 科学计算、积分、优化
- `sympy` (1.9) — 符号计算、微积分、方程求解
- `mpmath` — 高精度数学运算

## 使用方法

### 基本模板
```bash
python3 -c "
import numpy as np
import sympy as sp
from scipy import integrate, optimize
# ... 你的代码
print(result)
"
```

### 多行计算（用 heredoc）
```bash
python3 << 'EOF'
import numpy as np
x = np.array([1, 2, 3])
print(x.mean())
EOF
```

## 常用场景示例

### 1. 数值计算
```python
# 解方程组
import numpy as np
A = np.array([[3, 2], [1, 2]])
b = np.array([7, 5])
x = np.linalg.solve(A, b)
print(x)  # [1. 2.]
```

### 2. 符号计算（微积分）
```python
import sympy as sp
x = sp.Symbol('x')
f = sp.sin(x) * sp.exp(x)
integral = sp.integrate(f, (x, 0, sp.pi))
print(integral)
```

### 3. 求导
```python
import sympy as sp
x = sp.Symbol('x')
f = x**3 + 2*x**2 + 1
df = sp.diff(f, x)
print(df)  # 3*x**2 + 4*x
```

### 4. 数值积分
```python
from scipy import integrate
import numpy as np
def f(x):
    return np.sin(x) + x
result, error = integrate.quad(f, 0, np.pi)
print(result, error)
```

### 5. 写代码 & 运行脚本
```bash
# 写入临时脚本执行
cat > /tmp/script.py << 'EOF'
print("Hello from compute pro!")
EOF
python3 /tmp/script.py
```

## 注意事项
- 复杂计算建议用 heredoc 方式（避免引号嵌套问题）
- 输出结果用 print()，小萌读取 stdout 回答
- 如果计算结果太长，分段打印
- 需要安装新库时：`pip3 install 包名`（需主人确认）
