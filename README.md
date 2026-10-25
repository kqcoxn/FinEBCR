# FinFUND

**多源证据驱动的财务问答检索增强生成方法**

FinFUND（Financial Question Answering via Fusion of Unstructured and Numerical Data）围绕问题需求组织文本与数值证据，通过辅助事实关联衔接证据使用与任务求解，支持财报数值问答、表文混合问答和高校制度问答。本仓库提供可执行代码与自建高校财务问答数据集，通过OpenAI兼容API调用模型。

## 使用入口

- [安装与运行](method/README.md)：环境安装、API配置、数据路径和运行命令。
- [配置示例](method/config.example.json)：数据集、模型服务与通用运行参数。
- [输出与状态](docs/interfaces.md)：逐题结果、处理状态和请求回执。

## 数据

| 数据集 | 获取方式 |
| --- | --- |
| [FinQA](https://github.com/czyssrs/FinQA) | 从官方仓库自行获取，通过 `data_path` 指定JSON文件 |
| [TAT-QA](https://github.com/NExTplusplus/TAT-QA) | 从官方仓库自行获取，通过 `data_path` 指定JSON文件 |
| [高校财务问答](university-dataset/README.md) | 随仓库提供，包含86篇材料、349道问答及证据标注 |

FinQA与TAT-QA不随仓库分发，也不自动下载。原论文、具体数据文件和所需格式见[数据获取与格式](docs/data.md)。

## 仓库结构

| 目录 | 内容 |
| --- | --- |
| [method](method/README.md) | 方法代码、配置、运行入口与离线测试 |
| [university-dataset](university-dataset/README.md) | 高校财务材料、问答与数据说明 |
| [docs](docs/README.md) | 数据获取、文件格式与输出说明 |
