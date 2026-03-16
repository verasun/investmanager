# Contributing to InvestManager

感谢您有兴趣为 InvestManager 做贡献！

## 开发环境设置

### 前置要求

- Python 3.11+
- Docker & Docker Compose
- Git

### 设置步骤

1. **Fork 并克隆仓库**

```bash
git clone https://github.com/YOUR_USERNAME/investmanager.git
cd investmanager
```

2. **创建虚拟环境**

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
.\venv\Scripts\activate  # Windows
```

3. **安装开发依赖**

```bash
pip install -e ".[dev]"
pip install pytest pytest-asyncio pytest-cov
```

4. **配置环境变量**

```bash
cp .env.example .env
# 编辑 .env 文件
```

5. **运行测试**

```bash
pytest tests/ -v
```

## 代码规范

### Python 代码风格

- 遵循 PEP 8 规范
- 使用类型提示 (Type Hints)
- 函数和类添加文档字符串

```python
def calculate_ma(prices: list[float], period: int = 20) -> list[float]:
    """Calculate Moving Average.

    Args:
        prices: List of prices.
        period: MA period.

    Returns:
        List of MA values.
    """
    ...
```

### 提交信息格式

使用约定式提交：

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**类型 (type):**
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建/工具相关

**示例:**

```
feat(feishu): add command parser for bot messages

- Support Chinese and English commands
- Add regex-based parsing
- Include unit tests
```

## 分支策略

- `main`: 稳定发布版本
- `develop`: 开发分支
- `feature/*`: 功能分支
- `fix/*`: 修复分支
- `release/*`: 发布分支

## Pull Request 流程

1. 从 `develop` 创建功能分支
2. 进行开发并编写测试
3. 确保所有测试通过
4. 提交 Pull Request 到 `develop`
5. 等待代码审查

### PR 检查清单

- [ ] 代码遵循项目风格指南
- [ ] 已添加必要的测试
- [ ] 所有测试通过
- [ ] 文档已更新（如需要）
- [ ] 提交信息清晰

## 测试

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_sqlite.py -v

# 运行带覆盖率
pytest tests/ --cov=src --cov-report=html
```

### 测试规范

- 每个新功能都需要测试
- 使用 pytest fixtures 管理测试资源
- 异步测试使用 `@pytest.mark.asyncio`

## 项目结构

```
investmanager/
├── api/              # API 路由
├── config/           # 配置模块
├── src/
│   ├── data/         # 数据层
│   ├── cache/        # 缓存模块
│   ├── email/        # 邮件模块
│   ├── feishu/       # 飞书集成
│   ├── analysis/     # 分析模块
│   ├── backtest/     # 回测引擎
│   ├── strategies/   # 交易策略
│   └── report/       # 报告生成
├── tests/            # 测试文件
├── docs/             # 文档
└── scripts/          # 脚本工具
```

## 问题反馈

如果发现 bug 或有功能建议，请创建 Issue：

1. 使用清晰的标题描述问题
2. 提供复现步骤
3. 说明预期行为和实际行为
4. 附上相关日志或截图

## 许可证

贡献的代码将采用 MIT 许可证。