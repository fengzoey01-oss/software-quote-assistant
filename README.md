# 软件报价助手

从需求范围到报价工作稿，保留计价依据、缺口与版本差异。

这是个人定制工作流的通用公开版，提供可复用方法和虚构示例，不含真实公司或客户资料。适合：产品经理、售前及需要整理软件项目范围的团队。

## 能解决什么

从需求范围到报价工作稿，保留计价依据、缺口与版本差异。 以输入材料与验证证据为依据，不把生成内容当成已完成的业务结果。

## 运行条件

Python 3.9+；核心计算、XLSX 导出与测试仅用标准库。AI 整理需求时另需支持本地文件和脚本的客户端。

## 安装与调用

支持 Skills 的客户端：把整个仓库作为一个技能目录安装，目录名使用 `software-quote-assistant`。例如使用 Codex 时，复制到 `~/.codex/skills/software-quote-assistant`，然后重启客户端使其发现技能。已存在同名目录时先备份，不直接覆盖。

其他 AI 客户端也可以读取 `SKILL.md`，但本地脚本、文件写入、浏览及云端同步取决于客户端的工具与权限。

```text
用 $software-quote-assistant，根据这份需求拆分基础、选配和待确认项，先整理范围，再生成报价工作稿。
```

## 快速体验

```bash
python3 scripts/quote.py calculate examples/demo.json --output output/demo
python3 scripts/export_xlsx.py examples/demo.json --output output/demo
python3 -m unittest discover -s scripts -p 'test_*.py'
```

虚构示例的一次性含税金额为 **13,200.00 元**，只是用于验证计算的任意设定。默认选配项未计价、未选中；不能拿示例费率、税率或工时做真实报价依据。

输出 `internal.json`、`input-snapshot.json`、`internal.xlsx` 仅供内部使用。`customer.json`、`customer.xlsx` 使用客户字段白名单生成，但仍要人工检查公开文字。XLSX 不含隐藏成本表、不含公式、不含宏；金额以文本写入用于审阅，继续计算请修改输入后重新生成。

需要比较两个版本时：

```bash
python3 scripts/quote.py diff examples/demo.json private/revision.json --output output/diff.json
```

差异文件可能包含内部输入，不对外发送。

## 文件入口

- `SKILL.md`：触发条件、流程与边界。
- `agents/openai.yaml`：技能显示信息与默认调用语句。
- `examples/`：虚构输入或输出示例。
- `VALIDATION.md`：本次实际执行的检查及未验证范围。
- `NOTICE.md`：来源、公开范围与许可说明。

## 使用限制

人民币；同一输入使用一个税率；一次性与年度分别列示。不支持自动估算实际人力、税务判断、复杂分期或任意客户 Excel 模板。计算结果不会自动变成已审批报价。

## 资料与隐私

公开版本不依赖某家公司的客户表、内部文档标识、报价库或个人机器目录。真实使用时，输入、输出、截图及日志都需按资料权限管理；代码层的字段过滤无法识别自由文本里所有敏感信息。

本仓库不承诺生产环境效果。示例数字、名称和事件均为虚构，不可用作真实业务依据。当前许可状态见 [NOTICE.md](NOTICE.md)。
