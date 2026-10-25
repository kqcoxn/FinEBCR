# 输出与状态

每次运行在 `output_dir` 下创建独立目录，保存本次配置、逐题结果和请求回执。运行命令与路径设置见[安装与运行](../method/README.md)。

## 逐题结果

每道题的 `answer.json` 包含以下字段；任务专用字段和失败前尚未生成的字段可能缺省。

| 字段 | 含义 |
| --- | --- |
| `id`、`dataset`、`question` | 问题标识、数据集与问题文本 |
| `status` | 本题处理状态，见下表 |
| `answer` | 最终答案；TAT-QA多片段答案为字符串数组，弃答时可能为空值或依据不足标记 |
| `scale` | TAT-QA数值尺度：空字符串、`thousand`、`million`、`billion` 或 `percent` |
| `request_count` | 本题已记录的API调用次数，包括失败调用 |
| `error` | 失败原因（如有） |

结果还保留已生成的证据、事实关联和任务处理记录，供排查问题。TAT-QA数值答案按 `scale` 理解；例如 `answer="25"`、`scale="percent"` 表示25%。

## 处理状态

| 状态 | 含义 |
| --- | --- |
| `executed` | 数值计划检查与计算完成 |
| `answered` | 表文或制度回答通过格式检查 |
| `abstain` | 依据不足或空计划 |
| `invalid_plan` | 非法操作、引用、参数或计算 |
| `invalid_format` | 输出格式不合法，或请求长度等输入检查未通过 |
| `api_error` | 请求失败、响应缺失或未正常结束 |

`executed` 和 `answered` 表示流程完成，不是答案正确性评分。运行结束后的 `summary.json` 汇总题目数和各状态数量；出现上述三类错误状态时，程序返回非零退出码。

## 请求回执

`01-needs.json` 等回执保存阶段名称、请求体、收到的JSON响应、调用状态、耗时（秒）和服务返回的 `usage`，不保存认证头。用量缺失时为 `null`。调用前的长度检查失败时不产生API回执，原因记录在 `answer.json`。

回执中的 `completed` 表示已收到正常结束的文本响应，`invalid_response` 表示API响应格式或结束状态异常，`api_error` 表示连接或HTTP错误。回答内容是否符合任务格式由 `answer.json` 的状态反映。
