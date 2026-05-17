# RAG 系统调研与搭建教学

本文面向第一次系统理解 RAG 的读者，也作为 TooGraph 后续建设专业 RAG 能力的产品和工程参考。文中的“专业 RAG”不是指堆叠最多工具，而是指系统能稳定检索、可追溯引用、可评测、可维护、可审计，并能和权限、版本、业务流程一起工作。

调研日期：2026-05-21

## 1. 一句话结论

RAG 是 Retrieval-Augmented Generation，中文通常叫“检索增强生成”。它的核心不是训练模型，而是在模型回答前，从外部知识库检索相关资料，再把资料作为上下文交给模型生成回答。

一个能跑的 RAG Demo 通常是：

```text
上传文档 -> 切块 -> 生成 embedding -> 向量检索 -> 把 top-k chunk 塞给 LLM -> 输出答案
```

一个专业 RAG 系统通常是：

```text
数据接入
-> 解析清洗
-> 结构化切块
-> metadata / 权限 / 版本管理
-> 关键词检索 + 向量检索 + metadata filter
-> 多路召回融合
-> rerank
-> 上下文预算
-> 引用和证据校验
-> 生成回答
-> 评测、日志、反馈闭环
```

TooGraph 当前已经具备基础 Hybrid RAG 的核心骨架：知识库、chunk、SQLite FTS、本地 hash embedding、混合检索、citation 输出、知识库页面和 rebuild API。它可以支撑一个基础 RAG 系统，但要达到专业系统，还需要补强真实 embedding provider、用户文档导入、增量索引、reranker、权限隔离、RAG 评测和图模板化检索流程。

## 2. RAG 解决什么问题

LLM 有两个天然限制：

1. 模型不知道你的私有数据。
2. 模型训练知识会过期。

比如你问“我公司 2026 年差旅报销标准是什么”，模型本身无法可靠知道。RAG 的做法是先检索公司的制度文档，然后让模型基于检索结果回答。

RAG 的价值包括：

- 更新快：文档更新后重建索引即可，不必重新训练模型。
- 可追溯：答案可以附带来源、页码、chunk id、URL。
- 成本低：相比微调，RAG 更适合频繁变化的知识。
- 权限可控：可以按用户、部门、租户过滤可检索文档。
- 可评测：可以独立评估检索是否命中、回答是否忠实。

## 3. RAG 和微调的区别

RAG 是“查资料后回答”。微调是“改变模型参数或输出习惯”。

| 对比项 | RAG | 微调 |
| --- | --- | --- |
| 主要目标 | 补充外部知识 | 改变模型行为、风格或任务能力 |
| 数据更新 | 快，重建索引即可 | 慢，通常需要重新训练或再训练 |
| 私有知识问答 | 适合 | 不首选 |
| 固定输出格式 | 可做，但不如微调稳定 | 适合 |
| 引用来源 | 天然可保留 | 不天然保留 |
| 成本 | 主要是检索、embedding、上下文 token | 训练成本和维护成本更高 |

实用判断：

- 如果知识经常变，用 RAG。
- 如果答案必须引用资料，用 RAG。
- 如果你想让模型稳定模仿某种格式、语气或分类规则，可以考虑微调。
- 如果问题同时需要私有知识和固定行为，常见做法是 RAG + prompt/工具约束，必要时再微调。

## 4. RAG 的完整工作流

### 4.1 数据接入

数据接入是把资料带进系统。资料可能来自：

- Markdown、TXT、HTML、PDF、Word、PPT。
- 网页、产品文档、知识库、客服工单。
- 数据库、API、对象存储。
- 代码仓库、日志、会议纪要。

专业系统要记录来源和版本。例如一份政策 PDF 不只要保存正文，还要保存发布机构、发布日期、URL、页码和文件 hash。

### 4.2 文档解析

文档解析是把原始文件变成可检索文本。

不同格式难度不同：

- Markdown/TXT：相对简单。
- HTML：要去导航、广告、脚本和重复页脚。
- PDF：要处理页眉页脚、分栏、表格、扫描件、页码。
- Word/PPT：要保留标题层级和表格语义。
- 图片/扫描件：需要 OCR。

专业系统不能只追求“抽出文本”，还要保留“文本从哪里来”。否则模型给出引用时无法追溯。

### 4.3 切块

切块是把长文档拆成较小片段。因为模型上下文有限，检索系统也通常以 chunk 为基本单位。

常见切块方式：

- 固定长度切块：每 800 token 一块，简单但可能切断语义。
- 按标题切块：按 H1/H2/H3、章节、条款切，更适合文档问答。
- 按段落或句子切块：适合普通文本。
- 递归切块：优先按标题、段落、句子切，实在太长再按 token 切。
- 表格专用切块：保留表头和行上下文。
- 代码专用切块：按函数、类、文件结构切。

重要参数：

- chunk size：每块大小。太小会丢上下文，太大检索会变粗。
- overlap：相邻 chunk 的重叠内容。可以避免关键信息正好被切断。

OpenAI Retrieval 文档中默认静态切块示例提到 800 token chunk 和 400 token overlap。这个数值不是通用最优，但说明了一个原则：切块需要在完整语义和检索精度之间折中。

### 4.4 建索引

索引是为了快速找到相关内容。RAG 常见索引有三类：

1. 关键词索引。
2. 向量索引。
3. 结构化 metadata 索引。

关键词索引适合：

- 精确术语。
- 条款编号。
- 错误码。
- 人名、产品名、函数名。
- 原文包含某个关键词的问题。

向量索引适合：

- 同义表达。
- 模糊语义。
- 用户不会使用文档原词的问题。
- “这个规则大概是什么意思”这类语义问题。

metadata 索引适合：

- 只搜某个部门。
- 只搜某个版本。
- 只搜某个时间范围。
- 只搜当前用户有权限看的资料。

### 4.5 用户查询处理

用户的问题通常不是最佳检索 query。系统可能需要先做查询处理：

- 清洗问题：去掉无意义口语。
- 拆分问题：一个复杂问题拆成多个子问题。
- 查询改写：把“我能领吗”改成“青年人才住房补贴 申请条件 社保 学历 户籍”。
- 多查询：生成多个 query 分别检索。
- HyDE：先让模型生成一段假想答案，再用假想答案做检索。

查询处理的目标不是让问题变漂亮，而是提高召回率。

### 4.6 检索

检索就是从知识库里找候选 chunk。

常见检索方式：

- BM25 / FTS：关键词检索。
- Dense vector search：语义向量检索。
- Sparse vector search：稀疏向量检索，兼顾词项权重。
- Hybrid search：关键词 + 向量混合检索。
- Graph retrieval：通过实体和关系检索。
- Router retrieval：根据问题选择不同知识库或检索器。

专业系统通常不会只做一种检索。Pinecone、Qdrant、Weaviate、Milvus 等向量库文档都强调 hybrid search 的价值：语义检索能找到意思相近的内容，关键词检索能抓住精确词，两者互补。

### 4.7 融合和重排

检索第一轮通常追求“多找一些可能相关的候选”。之后需要融合和重排。

常见做法：

```text
BM25 取前 30 条
向量检索取前 30 条
metadata filter 过滤不可用结果
RRF 融合两个结果列表
reranker 精排前 50 条
取最终 top 5 给模型
```

RRF 是 Reciprocal Rank Fusion，用排名位置融合多个检索列表。Qdrant 官方 Hybrid Queries 文档展示了用 sparse 和 dense prefetch，再通过 RRF 融合的模式。

Reranker 是重排模型。它比向量检索慢，但更精细。常见架构是“快检索召回候选，慢 reranker 精排少量候选”。

### 4.8 上下文拼装

检索到 chunk 后，不能无脑塞给 LLM。需要控制上下文预算。

上下文拼装需要考虑：

- chunk 数量。
- 每个 chunk 的长度。
- 是否保留标题、来源、页码。
- 是否去重。
- 是否按重要性排序。
- 是否把相邻 chunk 合并。
- 是否保留 citation id。
- 是否过滤低置信度内容。

一个好的 RAG prompt 应该明确告诉模型：

- 只能基于给定资料回答。
- 资料不足时必须说明不足。
- 不要编造资料中没有的事实。
- 关键结论必须带引用。

### 4.9 回答生成

回答生成阶段要做两件事：

1. 把检索结果转成用户能理解的答案。
2. 把证据和答案绑定。

专业系统一般会要求输出结构：

```json
{
  "answer": "回答正文",
  "citations": [
    {
      "claim": "某个结论",
      "citation_id": "kb:policy:3",
      "source": "policy.pdf",
      "page": 12
    }
  ],
  "uncertainties": [
    "原文未说明申请截止日期"
  ]
}
```

这样 UI 可以展示引用，评测系统也能检查引用是否存在。

### 4.10 评测和反馈

RAG 不应靠“感觉好像能回答”验收。至少要评估：

- 检索有没有找回正确资料。
- 找回的资料是否大多相关。
- 答案是否被资料支持。
- 引用是否指向正确 chunk。
- 资料不足时是否拒绝编造。
- 响应延迟和成本是否可接受。

Ragas、LlamaIndex Evaluation 等工具都强调评测的重要性。Ragas 常见指标包括 faithfulness、answer relevancy、context precision、context recall。

## 5. 核心名词解释

### RAG

Retrieval-Augmented Generation，检索增强生成。系统先检索外部资料，再让 LLM 基于资料回答。

### LLM

Large Language Model，大语言模型。负责理解问题和生成回答。RAG 中 LLM 不是知识库本身，而是使用知识库结果的生成器。

### Knowledge Base

知识库。由一批文档、chunk、索引、metadata 和权限规则组成。一个系统可以有多个知识库，例如“产品文档库”“政策法规库”“客服 FAQ 库”。

### Document

文档。RAG 的原始资料单位，可以是一个 PDF、一篇网页、一条数据库记录或一个 Markdown 文件。

### Chunk

文档切出来的小片段。检索时通常返回 chunk，而不是整篇文档。

### Chunking

切块。把长文档拆成 chunk 的过程。

### Overlap

重叠区。相邻 chunk 之间重复一部分内容，避免信息被硬切断。

### Metadata

元数据。描述文档或 chunk 的结构化信息，如来源 URL、页码、标题、部门、权限、版本、时间。

### Embedding

向量嵌入。把文本转换成数字数组。意思接近的文本，向量距离通常更近。

### Dense Vector

稠密向量。多数 embedding 模型输出的向量都是 dense vector。它适合语义相似搜索。

### Sparse Vector

稀疏向量。大量维度为 0，只保存非零项和权重。适合关键词、术语和精确匹配。

### Vector Store

向量库。存储 embedding 并支持相似度搜索的系统。常见选项有 pgvector、Qdrant、Pinecone、Milvus、Weaviate、Elasticsearch。

### FTS

Full Text Search，全文搜索。SQLite FTS、PostgreSQL tsvector、Elasticsearch 都属于这一类。

### BM25

经典关键词相关性排序算法。它不懂语义，但对精确词匹配很有效。

### Hybrid Search

混合检索。把关键词检索和向量检索结合起来。适合生产系统，因为用户既会问语义问题，也会问精确术语、编号、名称。

### Top-k

取前 k 个结果。例如 top-5 就是取最相关的 5 个 chunk。

### Similarity

相似度。衡量 query 向量和 chunk 向量有多接近。常见度量包括 cosine、dot product、L2 distance。

### ANN

Approximate Nearest Neighbor，近似最近邻。为了加快大规模向量搜索，牺牲少量精度换速度。

### HNSW

Hierarchical Navigable Small World，一种常见 ANN 索引。pgvector、Qdrant、Milvus 等都支持或使用类似思路。

### IVFFlat

Inverted File Flat，一种向量索引。通常构建更快、内存较低，但速度和召回权衡不同于 HNSW。

### Reranker

重排模型。第一轮检索找候选，reranker 再精细判断 query 和候选 chunk 是否真正相关。

### Recall

召回率。正确资料有没有被找回来。RAG 系统如果 recall 低，模型再强也没法答对。

### Precision

精确率。找回来的资料里有多少真的有用。precision 低会浪费上下文，还会误导模型。

### Context Window

模型一次能读的最大上下文长度。

### Context Budget

上下文预算。决定检索结果、对话历史、系统指令、工具输出各占多少 token。

### Citation

引用。答案中标记依据来源的机制，例如 chunk id、页码、URL。

### Grounding

证据落地。要求回答建立在检索资料上，而不是模型自由发挥。

### Hallucination

幻觉。模型编造资料中没有的内容。

### Faithfulness

忠实度。答案是否被上下文支持。RAG 评测中常用于衡量是否幻觉。

### Context Precision

上下文精度。检索到的上下文中，相关内容的比例。

### Context Recall

上下文召回。回答所需的关键资料，有多少被检索到了。

### Query Rewrite

查询改写。把用户问题改写成更适合检索的 query。

### Multi-query Retrieval

多查询检索。一个问题生成多个 query，分别检索后合并结果。

### HyDE

Hypothetical Document Embeddings。先让模型生成一段假想答案，再用这段假想答案做检索。适合用户问题太短、关键词太少的情况。

### RRF

Reciprocal Rank Fusion。把多个检索结果列表按排名融合。

### GraphRAG

图增强 RAG。通过实体、关系、社区摘要等结构，支持跨文档、多跳关系和全局主题总结。Microsoft GraphRAG 文档把索引流程描述为从非结构化文本中抽取有意义结构化数据的 pipeline。

### RAPTOR

Recursive Abstractive Processing for Tree-Organized Retrieval。它把文本递归聚类并摘要成树，查询时可从不同抽象层级检索，适合长文档和多层级总结。

### Agentic RAG

智能体式 RAG。模型不只是固定检索一次，而是可以判断要不要检索、检索哪个知识库、是否继续补查、是否调用其他工具。

## 6. RAG 架构类型对比

### 6.1 Naive RAG

流程：

```text
文档 -> 切块 -> embedding -> 向量检索 top-k -> LLM 回答
```

优点：

- 简单。
- 成本低。
- 适合 Demo 和小规模 FAQ。

缺点：

- 容易漏召回。
- 不擅长精确术语。
- 引用不稳定。
- 无法处理复杂多跳问题。
- 没有评测很难知道哪里错。

### 6.2 Advanced RAG

Advanced RAG 会加入：

- query rewrite。
- hybrid search。
- metadata filter。
- reranker。
- 上下文压缩。
- 引用校验。
- RAG eval。

这是大多数业务系统应达到的最低专业水位。

### 6.3 Modular RAG

模块化 RAG 把系统拆成可替换模块：

```text
loader -> parser -> chunker -> embedder -> retriever -> reranker -> prompt builder -> generator -> evaluator
```

好处是每个模块可以独立测试和替换。TooGraph 的图优先架构天然适合这种方式。

### 6.4 Agentic RAG

Agentic RAG 让 LLM 参与决策：

- 是否需要检索。
- 检索哪个知识库。
- 是否拆成子问题。
- 是否继续补充检索。
- 是否调用网页搜索、数据库、文件工具。

适合研究助手、复杂业务分析、多轮任务。缺点是延迟、成本、可控性更难管理。

### 6.5 GraphRAG

GraphRAG 适合：

- 跨文档关系分析。
- “这个语料的主要主题是什么”。
- “这些事件之间有什么关联”。
- 法律、金融、情报、企业知识图谱。

GraphRAG 通常会构建实体、关系、社区、摘要。成本高于普通 RAG，不适合一上来就做所有场景。

### 6.6 RAPTOR / 层级 RAG

RAPTOR 类方法适合长文档。它不是只存底层 chunk，还会存上层摘要节点。查询时既能拿细节，也能拿高层摘要。

适合：

- 长报告问答。
- 书籍问答。
- 复杂政策文档总结。
- 多章节归纳。

### 6.7 Multimodal RAG

多模态 RAG 处理文本之外的信息：

- 图片。
- 图表。
- 扫描件。
- 视频帧。
- 音频转写。

难点在于 OCR、图表理解、版面还原、媒体引用和证据展示。

## 7. 专业 RAG 系统和 Demo 的关键差异

### 7.1 数据治理

Demo 只关心“能不能读文件”。专业系统要关心：

- 文件来源。
- 版本。
- 删除后索引是否同步删除。
- 是否重复导入。
- 是否有权限读取。
- 文档解析是否失败。
- chunk 是否可追溯到原始位置。

### 7.2 检索质量

专业系统需要明确回答这些问题：

- 用户问法和文档写法不一致时能否搜到？
- 专有名词、错误码、政策编号能否精确匹配？
- 是否能过滤过期版本？
- 是否能过滤无权限文档？
- 是否能处理多问题查询？
- 是否能发现资料不足？

### 7.3 引用可信度

专业系统不能只在答案末尾贴几个来源。更好的引用是“结论级引用”：

```text
结论 A 来自 citation 1 和 citation 3。
结论 B 来自 citation 2。
资料未说明 C，因此不能确认。
```

### 7.4 可观测性

RAG 出错时，必须能定位错在哪一步：

- query rewrite 是否改坏了？
- 检索是否没命中？
- reranker 是否排序错误？
- prompt 是否塞了错误上下文？
- LLM 是否无视证据？
- 引用是否丢失？

因此需要保留 run detail、检索结果、分数、prompt 片段、生成结果和评测记录。

### 7.5 安全和权限

RAG 系统常见安全问题：

- 用户越权检索别人的文档。
- 文档里有 prompt injection。
- 模型把敏感内容输出给无权限用户。
- 删除的文档仍出现在索引。
- 多租户数据串库。

专业系统必须把权限放在检索层，而不是只靠 prompt 说“不要泄漏”。

## 8. 技术选型调研

### 8.1 OpenAI Retrieval / File Search

OpenAI Retrieval 使用 vector stores 做语义搜索。File Search 是 Responses API 中的托管工具，可以让模型检索上传到 vector store 的文件。官方文档说明 vector store 会承载语义搜索，文件加入 vector store 后会进行 chunk、embedding 和 indexing。

适合：

- 快速搭建。
- 不想自己维护向量库。
- 使用 OpenAI 托管检索能力。

限制：

- 检索内部细节可控性较低。
- 深度定制、私有部署、复杂权限可能需要自建系统。

### 8.2 LangChain

LangChain 更偏应用编排。它提供 document loaders、retrievers、vector store 集成、RAG agent 等能力。官方把 RAG 描述为用上下文特定信息增强 LLM 回答。

适合：

- 快速组装应用。
- 多工具、多模型、多向量库集成。
- Agentic RAG。

限制：

- 抽象层多，生产系统需要控制复杂度。
- 最终质量仍取决于数据、检索和评测。

### 8.3 LlamaIndex

LlamaIndex 更偏数据到 LLM 的索引和查询框架。官方把 RAG 分为 Loading、Indexing、Storing、Querying、Evaluation 五个阶段，并解释了 Document、Node、Retriever、Router、Node Postprocessor、Response Synthesizer 等概念。

适合：

- 需要多数据源接入。
- 需要索引、retriever、query engine 抽象。
- 需要评测和调试 RAG 流程。

限制：

- 仍需要根据业务设计文档解析、权限和部署架构。

### 8.4 pgvector

pgvector 是 PostgreSQL 的向量扩展。它支持 exact 和 approximate nearest neighbor search，并支持 HNSW、IVFFlat 索引。

适合：

- 已经使用 PostgreSQL。
- 中小规模知识库。
- 希望 metadata、权限和向量存在同一个数据库。

限制：

- 超大规模向量检索和复杂 ANN 调优不如专用向量库。
- 混合检索通常需要自己结合 PostgreSQL FTS。

### 8.5 Qdrant

Qdrant 是专用向量搜索引擎。官方文档支持 dense、sparse、hybrid queries、RRF、多阶段查询、metadata filtering。

适合：

- 需要自托管向量库。
- 需要 hybrid search。
- 需要 payload filter。
- 需要较好的向量检索性能。

### 8.6 Pinecone

Pinecone 是托管向量数据库。官方 Hybrid Search 文档强调 semantic search 和 lexical search 各有局限，hybrid search 可以组合两者。

适合：

- 不想自运维。
- 需要托管扩展能力。
- 团队愿意接受云服务成本。

### 8.7 Weaviate

Weaviate 支持 hybrid search，将 vector search 和 BM25 结果融合。官方文档说明 hybrid 会并行执行向量搜索和关键词搜索，并融合分数。

适合：

- 需要对象存储 + 向量搜索 + BM25。
- 希望内置 hybrid。

### 8.8 Milvus

Milvus 适合较大规模向量检索。官方文档支持 dense、sparse、hybrid retrieval，多向量字段和 weighted reranker。

适合：

- 大规模向量数据。
- 高并发检索。
- 多向量、多模态场景。

## 9. 评测体系

### 9.1 为什么 RAG 必须评测

RAG 失败有多种形态：

- 检索没找对。
- 找对了但排序太靠后。
- 上下文塞太多，模型忽略关键内容。
- 模型编造。
- 引用错。
- 答案对但来源不对。
- 权限过滤错。

只看最终答案很难定位问题。因此评测要拆成检索评测和生成评测。

### 9.2 检索评测

检索评测关注“资料找得对不对”。

常见指标：

- Recall@k：正确资料是否出现在前 k 条。
- Precision@k：前 k 条中相关资料比例。
- MRR：第一个正确结果排得多靠前。
- nDCG：相关结果排序质量。
- Hit Rate：是否至少命中一个正确结果。

### 9.3 生成评测

生成评测关注“答案是否正确”。

常见指标：

- Faithfulness：答案是否被上下文支持。
- Answer Relevancy：答案是否回答了问题。
- Citation Accuracy：引用是否支持对应结论。
- Completeness：关键点是否完整。
- Refusal Accuracy：资料不足时是否正确拒答。

### 9.4 RAG 评测集怎么做

一个专业 RAG 评测集至少包含：

- 用户问题。
- 标准答案或答案要点。
- 应命中的文档或 chunk。
- 不应引用的干扰文档。
- 预期引用。
- 权限场景。
- 过期版本场景。
- 资料不足场景。

示例：

```json
{
  "question": "应届硕士能申请青年人才住房补贴吗？",
  "expected_claims": [
    "需要满足学历条件",
    "需要满足就业或社保条件",
    "是否应届取决于政策定义"
  ],
  "expected_citations": ["kb:policy:12", "kb:policy:14"],
  "must_not_claim": [
    "一定可以申请"
  ]
}
```

## 10. 小白搭建 RAG 的推荐路线

### 阶段一：最小可用版

目标：能导入少量文档，问问题，返回带引用的答案。

组件：

- 文档上传。
- 文本解析。
- 简单切块。
- embedding。
- 向量库。
- top-k 检索。
- prompt 模板。
- citation 输出。

验收标准：

- 能回答文档里明确出现的问题。
- 答案能展示来源。
- 资料不足时不胡编。

### 阶段二：Hybrid RAG

目标：提升检索质量。

新增能力：

- BM25 / FTS。
- dense vector search。
- metadata filter。
- RRF 或分数融合。
- reranker。
- query rewrite。

验收标准：

- 精确词问题和语义问题都能命中。
- top-5 里能稳定出现正确 chunk。
- 干扰文档不会经常排第一。

### 阶段三：专业生产版

目标：可上线给真实用户使用。

新增能力：

- 权限过滤。
- 增量索引。
- 文档版本。
- 删除一致性。
- 检索和生成日志。
- 评测集。
- 成本和延迟监控。
- prompt injection 防护。

验收标准：

- 不越权。
- 可追溯。
- 可回放。
- 可评测。
- 失败可定位。

### 阶段四：高级 RAG

目标：处理复杂知识场景。

可选能力：

- GraphRAG。
- RAPTOR。
- 多模态 RAG。
- Agentic RAG。
- 领域专用 reranker。
- 自动知识更新。

## 11. TooGraph 当前能力评估

### 11.1 已具备能力

TooGraph 当前已经有以下基础：

- `backend/app/knowledge/loader.py` 提供知识库导入、切块、搜索、embedding rebuild。
- `backend/app/core/storage/database.py` 中已有 `knowledge_bases`、`knowledge_documents`、`knowledge_chunks`、`knowledge_chunk_embeddings` 和 SQLite FTS 表。
- `search_knowledge()` 会返回 `citation_id`、`chunk_id`、`summary`、`content`、`score`、`metadata` 和 retrieval 信息。
- `_search_ranked_rows()` 已经合并 FTS、LIKE 和向量候选，再按关键词分数与向量分数重排。
- `backend/app/core/runtime/knowledge_retrieval.py` 可以组装 `knowledge_context` 和 `citations`。
- Knowledge 页面支持知识库列表、搜索、官方知识库导入、rebuild 和删除。
- `toograph_context_fanout` Action 已能读取 knowledge context。

这说明 TooGraph 不是从零开始，而是已经有基础 Hybrid RAG 底座。

### 11.2 当前短板

当前短板主要有：

- 默认 embedding 是 `local-hash` baseline，不是真正语义 embedding。
- 用户自定义文档导入流程还不完整。
- 没有独立通用的 `knowledge_retrieval` Action 作为正式 RAG 检索节点。
- 没有专业 reranker。
- 没有完整 RAG eval 套件。
- 权限、租户、文档级 ACL 需要在检索层明确建模。
- citation 可以输出，但还需要结论级引用校验。
- 对 PDF、表格、图片、扫描件等复杂文档的解析能力需要增强。

### 11.3 TooGraph 最推荐的建设方向

TooGraph 不应把 RAG 做成隐藏后端逻辑，而应做成图优先、可审计的模板流程：

```text
Input: 用户问题
Input: 知识库选择
LLM: 查询理解和改写
Action: knowledge_retrieval
LLM: 证据审查
Condition: 资料是否足够
Action/LLM: 可选补充检索
LLM: 生成带引用答案
Output: 答案、citations、证据摘要、风险提示
```

这样符合 TooGraph 的产品原则：低层能力由 Action 执行，多步智能由图模板表达，运行过程可审计。

## 12. TooGraph RAG 路线图建议

### 12.1 P0：做成可用的标准 RAG 模板

新增 `knowledge_retrieval` Action：

输入：

- `query`
- `knowledge_base`
- `limit`
- `metadata_filter`
- `retrieval_mode`

输出：

- `knowledge_context`
- `results`
- `citations`
- `retrieval_report`
- `warnings`

新增官方模板：

```text
rag_question_answering
```

节点：

- 输入问题。
- 输入知识库。
- 改写 query。
- 调用检索 Action。
- 审查证据是否足够。
- 生成答案。
- 输出 citations。

### 12.2 P1：接入真实 embedding 和 reranker

embedding provider：

- OpenAI embeddings。
- 本地 BGE-M3。
- nomic-embed-text。
- Jina embeddings。

reranker：

- BGE reranker。
- Jina reranker。
- Cohere Rerank。
- 本地 cross-encoder。

注意：embedding model、维度、provider、版本必须写入知识库 metadata。否则以后换模型会导致索引不可解释。

### 12.3 P2：用户文档知识库

需要支持：

- 上传文件。
- 文件夹导入。
- 网页导入。
- 重新同步。
- 增量更新。
- 删除同步。
- 解析失败报告。
- 文档版本。

输出 artifact：

- 导入报告。
- chunk 报告。
- embedding 报告。
- 错误列表。

### 12.4 P3：RAG Eval

评测对象：

- 检索结果。
- 回答质量。
- 引用质量。
- 权限过滤。
- 延迟和成本。

评测指标：

- Recall@k。
- Precision@k。
- Faithfulness。
- Citation Accuracy。
- Answer Relevancy。
- Refusal Accuracy。

### 12.5 P4：高级能力

按业务需要再加：

- GraphRAG。
- RAPTOR。
- 多模态解析。
- Agentic RAG。
- 自动知识刷新。
- 领域图谱。

## 13. 常见错误和避坑

### 错误一：只做向量检索

只做向量检索会漏掉精确词。比如错误码、政策条款、函数名、产品型号，关键词检索往往更可靠。

建议：默认做 hybrid search。

### 错误二：chunk 越大越好

chunk 太大，检索结果会包含太多无关内容，模型容易被噪声干扰。

建议：按文档结构切块，并保留 overlap。

### 错误三：没有 metadata

没有 metadata，就无法做权限、版本、来源、时间过滤。

建议：文档导入时强制写入 source、path、title、section、created_at、version、acl。

### 错误四：没有评测集

没有评测集，就不知道改动是变好还是变坏。

建议：每个知识库至少维护一组核心问答和应命中 chunk。

### 错误五：引用只是装饰

如果引用不能支持结论，那引用没有意义。

建议：做 claim -> citation 的结构化映射。

### 错误六：把权限交给 prompt

prompt 不能作为安全边界。

建议：权限必须在检索前或检索时过滤。

### 错误七：忽略删除一致性

文档删除后，如果向量索引还保留 chunk，会造成过期资料或敏感资料泄漏。

建议：每个 chunk 关联 document id 和 version，删除时同步删除索引。

## 14. 推荐系统设计

### 14.1 数据表建议

```text
knowledge_bases
- kb_id
- label
- description
- owner
- default_embedding_provider
- default_embedding_model
- created_at
- updated_at

knowledge_documents
- doc_id
- kb_id
- title
- source_uri
- source_kind
- version
- content_hash
- acl
- metadata_json
- status
- created_at
- updated_at

knowledge_chunks
- chunk_id
- doc_id
- kb_id
- ordinal
- title
- section
- content
- content_hash
- token_count
- page
- metadata_json

knowledge_embeddings
- chunk_id
- provider
- model
- dimension
- embedding
- content_hash
- created_at

knowledge_retrieval_logs
- run_id
- query
- rewritten_query
- kb_id
- filters
- retrieved_chunk_ids
- scores
- selected_chunk_ids
- latency_ms
- created_at
```

### 14.2 检索流程建议

```text
1. 用户问题进入图
2. LLM 改写 query
3. Action 读取知识库和 filter
4. FTS 检索 top 30
5. 向量检索 top 30
6. 合并去重
7. metadata / ACL 过滤
8. reranker 排序
9. 组装 top 5 context
10. LLM 生成答案和 citation
11. 输出答案、证据、检索报告
```

### 14.3 Prompt 建议

```text
你是一个基于证据回答问题的助手。
只能使用 Sources 中的信息回答。
如果 Sources 不足以回答，明确说明缺少什么。
每个关键结论后必须标注 citation_id。
不要编造来源、日期、金额、条件或流程。
```

### 14.4 输出结构建议

```json
{
  "answer": "面向用户的答案",
  "claims": [
    {
      "text": "关键结论",
      "citation_ids": ["kb:example:1"]
    }
  ],
  "citations": [
    {
      "citation_id": "kb:example:1",
      "chunk_id": "example-doc:3",
      "title": "文档标题",
      "source": "https://example.com/doc",
      "section": "申请条件"
    }
  ],
  "uncertainties": [
    "资料未说明截止日期"
  ]
}
```

## 15. 学习顺序建议

如果你是小白，建议按这个顺序理解：

1. 先理解 RAG 不是训练模型，而是检索资料。
2. 再理解 chunk、embedding、vector store。
3. 然后理解为什么只用向量检索不够。
4. 接着理解 hybrid search 和 reranker。
5. 再理解 citation 和 grounding。
6. 最后理解 eval、权限、版本、监控。

不要一开始就做 GraphRAG 或 Agentic RAG。先把基础 RAG 的数据、检索、引用、评测做好。

## 16. 参考资料

- OpenAI Retrieval Guide: https://platform.openai.com/docs/guides/retrieval
- OpenAI File Search Guide: https://platform.openai.com/docs/guides/tools-file-search/
- OpenAI Embeddings Guide: https://platform.openai.com/docs/guides/embeddings
- LangChain Retrieval Docs: https://docs.langchain.com/oss/python/langchain/retrieval
- LangChain RAG Agent Docs: https://docs.langchain.com/oss/python/langchain/rag
- LlamaIndex Introduction to RAG: https://docs.llamaindex.ai/en/stable/understanding/rag/
- Pinecone Hybrid Search: https://docs.pinecone.io/guides/search/hybrid-search
- Qdrant Hybrid Queries: https://qdrant.tech/documentation/concepts/hybrid-queries/
- Qdrant Vectors: https://qdrant.tech/documentation/concepts/vectors/
- Weaviate Hybrid Search: https://weaviate.io/developers/weaviate/concepts/search/hybrid-search
- pgvector README: https://github.com/pgvector/pgvector
- Milvus Hybrid Search: https://milvus.io/docs/multi-vector-search.md
- Ragas Context Precision: https://docs.ragas.io/en/v0.2.10/concepts/metrics/available_metrics/context_precision/
- Microsoft GraphRAG Docs: https://microsoft.github.io/graphrag/
- Lewis et al. 2020, Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks: https://arxiv.org/abs/2005.11401
- RAPTOR, Recursive Abstractive Processing for Tree-Organized Retrieval: https://arxiv.org/abs/2401.18059
- GraphRAG paper, From Local to Global: https://arxiv.org/abs/2404.16130
