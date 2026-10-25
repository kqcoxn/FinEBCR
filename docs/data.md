# 数据说明

## FinQA

- 原论文：[FinQA: A Dataset of Numerical Reasoning over Financial Data](https://aclanthology.org/2021.emnlp-main.300/)（EMNLP 2021）。
- 代码与数据：[czyssrs/FinQA](https://github.com/czyssrs/FinQA)。
- 有标注测试集：[dataset/test.json](https://github.com/czyssrs/FinQA/blob/main/dataset/test.json)，1,147题。

从官方仓库自行获取JSON文件，保留原始结构，将配置中的 `dataset` 设为 `finqa`，`data_path` 指向该文件。每条记录对应一个问题和给定财报材料。

| 字段 | 含义 |
| --- | --- |
| `id` | 问题标识 |
| `pre_text` / `post_text` | 表格前后的文本 |
| `table` | 表格，首行为表头 |
| `qa.question` | 问题 |
| `qa.exe_ans` | 参考答案 |
| `qa.program` | 参考计算程序 |
| `qa.gold_inds` | 支持证据标注 |

运行读取问题和给定材料，参考答案及标注字段保留在原始文件中，无需删除。

## TAT-QA

- 原论文：[TAT-QA: A Question Answering Benchmark on a Hybrid of Tabular and Textual Content in Finance](https://aclanthology.org/2021.acl-long.254/)（ACL 2021）。
- 代码与数据：[NExTplusplus/TAT-QA](https://github.com/NExTplusplus/TAT-QA)。
- 有标注测试集：[dataset_raw/tatqa_dataset_test_gold.json](https://github.com/NExTplusplus/TAT-QA/blob/master/dataset_raw/tatqa_dataset_test_gold.json)，277组上下文、1,663题。

从官方仓库自行获取JSON文件，将配置中的 `dataset` 设为 `tatqa`，`data_path` 指向该文件。用于答案评价时选择带参考答案的 `test_gold` 文件。原始数据按表文上下文组织，一个上下文对应多个问题；无需预先展平。

| 字段 | 含义 |
| --- | --- |
| `table.uid` / `table.table` | 表格标识与内容 |
| `paragraphs[].order` / `text` | 段落次序与文本 |
| `questions[].uid` / `question` | 问题标识与文本 |
| `questions[].answer` | 参考答案 |
| `questions[].answer_type` | 算术、计数、单片段或多片段类型 |
| `questions[].scale` | 数值尺度 |

保留表格、段落次序与问题之间的原始对应关系。FinQA与TAT-QA均使用每题给定的财报材料。

## 高校财务数据集

[corpus.json](../university-dataset/corpus.json)保存86篇材料；[qa.json](../university-dataset/qa.json)保存349道问题。检索范围是完整材料库。

| 文件与字段 | 含义 |
| --- | --- |
| `corpus[].title` | 材料标题 |
| `corpus[].category` | 材料类别 |
| `corpus[].body` | 材料正文 |
| `corpus[].source` / `author` / `published_at` | 材料附带的来源、作者与发布日期元数据，按记录提供 |
| `qa[].query` | 问题 |
| `qa[].answer` | 参考答案 |
| `qa[].question_type` | 查询、判断或推理 |
| `qa[].evidence_list[].title` | 标注证据对应的材料标题 |
| `qa[].evidence_list[].fact` | 标注的支持内容 |

`evidence_list[].title` 对应材料库标题，`fact` 保存标注内容。运行使用问题与完整材料库。

[catalog.json](../university-dataset/catalog.json)的 `index` 为材料在 `corpus.json` 中从0开始的位置，`characters` 为正文字数；问答顺序沿用 `qa.json` 的数组次序。统计及校验值见 [metadata.json](../university-dataset/metadata.json)。
