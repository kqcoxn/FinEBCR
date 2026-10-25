# 运行 FinFUND

运行需要Python 3.11–3.13、uv和OpenAI兼容模型服务。分词器与重排模型在本地加载。

## 安装与运行

在仓库根目录执行：

```powershell
uv sync --project method
Copy-Item method/config.example.json method/config.local.json
```

先按[数据获取说明](../docs/data.md)自行下载FinQA或TAT-QA，填写配置中的 `dataset` 与 `data_path`。例如使用FinQA时，可将 `data_path` 设为 `D:/datasets/FinQA/dataset/test.json`。仓库不内置或自动下载这两套数据。

编辑配置中的 `api.base_url` 和 `api.model`，分别填写服务的API基础地址与实际模型标识。程序在基础地址后追加 `/chat/completions`。密钥从 `api_key_env` 指定的环境变量读取，不写入配置文件。

```powershell
$env:FINFUND_API_KEY = "你的API密钥"
uv run --project method python method/run.py --config method/config.local.json --dry-run
uv run --project method python method/run.py --config method/config.local.json --limit 1
```

Linux/macOS可用 `cp` 复制配置，使用 `export FINFUND_API_KEY="..."` 设置环境变量，其余命令相同。

本地模型服务同样使用OpenAI兼容端点，例如 `http://localhost:1234/v1`。不要求认证时将 `api_key_env` 设为空字符串。服务须支持 `chat/completions`、JSON对象输出与非流式响应。思考模式等服务扩展参数可放入 `extra_body`，具体字段由所用服务决定。

`--dry-run` 仅检查配置、数据读取和题目范围，不加载模型、不联网、不生成回答。首次正式运行时会自动下载缺失文件：`runtime.tokenizer` 只下载分词器文件，`runtime.reranker` 下载分词器和重排模型权重；后续复用缓存。两项均可填写已下载文件的本地绝对路径。`device` 支持 `auto`、`cpu`、`cuda`，自动模式优先使用可用CUDA。

## 数据与范围

切换数据集时，同时更新配置中的名称与文件路径。例如使用TAT-QA：

```json
{
  "dataset": "tatqa",
  "data_path": "D:/datasets/TAT-QA/dataset_raw/tatqa_dataset_test_gold.json"
}
```

以上仅展示需修改的字段，其余API与运行参数保留。使用仓库内高校数据时，将 `dataset` 设为 `university`，`data_path` 和 `corpus_path` 设为空字符串；也可分别指定问答与材料库文件。

`offset` 是从0开始的问题序号，`limit` 是问题数；`limit=0` 处理该起点之后的全部问题。命令行覆盖配置同名项。FinQA和TAT-QA使用每题给定材料，高校问答检索完整制度材料库。

## 配置

| 配置 | 用途 |
| --- | --- |
| `dataset` | `finqa`、`tatqa` 或 `university` |
| `data_path` | FinQA／TAT-QA必须指定下载后的JSON文件；高校问答省略或留空时使用仓库内 `qa.json` |
| `corpus_path` | 高校材料库路径；省略或留空时使用仓库内 `corpus.json` |
| `limit`、`offset`、`output_dir` | 问题范围与结果目录 |
| `api.base_url`、`api.model`、`api.api_key_env` | 模型服务和密钥环境变量 |
| `api.temperature`、`max_output_tokens`、`max_input_tokens` | 生成参数和请求长度控制 |
| `api.timeout_seconds`、`extra_body` | 请求超时及服务扩展参数 |
| `runtime.tokenizer`、`reranker`、`device` | 分词器、语义重排模型和设备 |
| `runtime.evidence_tokens`、`candidate_count` | 证据预算和重排候选规模 |

数据与结果的相对路径按配置文件所在目录解析；`output_dir` 省略或留空时使用配置目录下的 `outputs/`。证据预算统计序列化来源对象；加入问题、辅助信息和提示后，完整请求另受 `max_input_tokens` 限制。长度按配置的分词器计量，不等同于服务端计费token。

## 输出

每次运行创建独立目录，已有结果不会被覆盖：

- `run.json`：运行参数、问题ID和源码哈希，不含API密钥。
- `00000/answer.json`：答案、状态、需求、证据、事实关联，以及计算轨迹或制度单元。
- `00000/01-needs.json` 等：各阶段请求、响应、耗时及服务返回的用量。
- `summary.json`：题目数和输出状态计数。

非法输出、弃答和请求失败均保留，不自动重试模型请求。结果字段、状态含义及退出码见[输出与状态](../docs/interfaces.md)。

## 离线检查

```powershell
uv run --project method python -m unittest discover -s method/tests -v
```

测试使用临时样例和模拟API响应，不调用在线模型，也不需要下载FinQA或TAT-QA。

## 代码格式

使用Ruff统一格式，规则保存在 [pyproject.toml](pyproject.toml)：4空格缩进、88字符目标行宽、双引号及LF换行。在仓库根目录执行：

```powershell
uvx ruff==0.17.2 format method
uvx ruff==0.17.2 format --check method
uvx ruff==0.17.2 check method
```
