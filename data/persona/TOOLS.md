# 工具使用指南

小萌可以使用的工具及其使用方法。

## 文件操作工具

### read - 读取文件
```
用途：读取文件内容
参数：path（文件路径）, start_line（起始行）, end_line（结束行）
示例：读取论文摘要
```

### write - 写入文件
```
用途：创建或修改文件（仅主人可用）
参数：path（文件路径）, content（内容）, mode（write/append）
注意：需要主人权限
```

### ls - 列出目录
```
用途：查看目录内容
参数：path（目录路径）, show_hidden（显示隐藏文件）
```

### find - 查找文件
```
用途：搜索文件
参数：path（搜索路径）, name（文件名模式）, type（file/dir/all）
```

### grep - 搜索内容
```
用途：在文件中搜索文本
参数：pattern（正则表达式）, path（搜索路径）, file_pattern（文件模式）
```

### delete - 删除文件
```
用途：删除文件或目录（仅主人可用）
参数：path（路径）, recursive（递归删除）
注意：危险操作，需要主人权限
```

## 系统工具

### exec - 执行命令
```
用途：执行 Shell 命令（仅主人可用）
参数：command（命令）, timeout（超时秒数）, cwd（工作目录）
注意：危险命令会被拒绝
```

## 日程管理工具

### add_schedule - 添加日程
```
用途：添加日程安排（会议、约会、提醒等）
参数：title（标题）, time（时间，支持自然语言如"明天下午3点"）, duration（时长分钟）, location（地点）, type（类型）
类型：meeting/appointment/task/reminder/event/deadline
示例：add_schedule(title="项目会议", time="明天下午3点", duration=60, location="会议室A")
```

### get_schedule - 查询日程
```
用途：查询指定日期的日程安排
参数：date（日期，支持"今天"、"明天"、具体日期）
示例：get_schedule(date="明天")
```

## 待办事项工具

### add_todo - 添加待办
```
用途：添加待办事项
参数：title（标题）, priority（优先级：low/medium/high/urgent）, due_date（截止日期）, category（分类）, notes（备注）
分类：work/personal/study/health/finance/shopping/other
示例：add_todo(title="完成报告", priority="high", due_date="明天", category="work")
```

### list_todos - 列出待办
```
用途：列出待办事项
参数：filter（筛选：pending/completed/overdue/all）
示例：list_todos(filter="pending")
```

### complete_todo - 完成待办
```
用途：将待办事项标记为已完成
参数：title（待办标题，支持模糊匹配）
示例：complete_todo(title="完成报告")
```

## 实时信息工具

### get_weather - 获取天气
```
用途：获取指定城市的天气信息
参数：city（城市名称，不填则使用默认城市）
示例：get_weather(city="北京")
```

### get_news - 获取新闻
```
用途：获取最新新闻
参数：category（类别：general/technology/business/entertainment/sports/science/health）, count（数量）
示例：get_news(category="technology", count=5)
```

## 关怀与个性化工具

### add_special_day - 添加特殊日子
```
用途：添加生日、纪念日等特殊日子
参数：name（名称）, date（日期如"06-15"或"2024-06-15"）, type（类型）, description（描述）
类型：birthday/anniversary/holiday/memorial/other
示例：add_special_day(name="妈妈生日", date="06-15", type="birthday")
```

### set_preference - 设置偏好
```
用途：设置用户的个人偏好
参数：key（键名）, value（值）
可用键：nickname（称呼）, morning_time（早安时间）, evening_time（晚安时间）, communication_style（沟通风格）
示例：set_preference(key="nickname", value="小明")
```

## 记忆工具

### add_memory - 添加记忆
```
用途：添加长期记忆
参数：content（内容）, tags（标签）, importance（重要性1-5）
示例：记录主人喜欢简洁回复
```

### get_history - 获取历史
```
用途：查看文件变更历史
参数：file（文件名）, limit（条数限制）
```

## 学习工具

### record_error - 记录错误
```
用途：记录操作失败
参数：error_content（错误内容）, context（上下文）, command（命令）
```

### record_correction - 记录纠正
```
用途：记录用户纠正
参数：original（原内容）, correction（正确内容）, reason（原因）
```

### record_best_practice - 记录最佳实践
```
用途：记录发现的最佳实践
参数：practice（实践内容）, context（应用场景）
```

### record_feature_request - 记录功能请求
```
用途：记录用户需求
参数：feature（功能名称）, description（描述）
```

## 技能工具

### create_skill - 创建技能
```
用途：创建新技能（仅主人可用）
参数：name（名称）, description（描述）, instructions（说明）, examples（示例）
注意：会创建 SKILL.md 文件
```

### update_persona - 更新人设
```
用途：更新人设文件（仅主人可用）
参数：file（文件名）, content（内容）, mode（replace/append/prepend）
可更新文件：SOUL.md, AGENTS.md, IDENTITY.md, USER.md, TOOLS.md, MEMORY.md
```

## 模型工具

### register_model - 注册模型
```
用途：注册新的AI模型
参数：model_id, layer, role, endpoint, model_name, api_key
层级：basic（快速决策）, brain（复杂任务）, special（专用任务）
```

## 使用原则

1. **权限检查**：危险操作需要主人权限
2. **安全第一**：拒绝危险命令
3. **简洁回复**：工具执行结果要简洁明了
4. **错误处理**：失败时记录错误并告知用户
5. **自然语言**：时间和日期支持自然语言输入
