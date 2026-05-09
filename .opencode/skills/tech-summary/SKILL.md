---
name: tech-summary
description: 当需要对采集的技术内容进行深度分析总结时使用此技能
allowed-tools:
  - Read
  - Grep
  - Glob
  - WebFetch
---

# Tech Summary 技能

## 使用场景

用于对 `knowledge/raw/` 中的最新采集结果做深度分析并输出结构化总结。

## 执行步骤（4步）

1. **读取最新采集文件**  
   读取 `knowledge/raw/` 下最新的采集文件。

2. **逐条深度分析**  
   对每个项目输出：摘要（<=50字）、技术亮点 2-3 个、评分（1-10）及理由、标签建议。

3. **趋势发现**  
   总结共同主题、重复出现的技术方向和新概念。

4. **输出分析结果 JSON**  
   按指定 JSON 结构整理结果；支持写文件时写入目标路径，否则输出完整 JSON 内容。

## 注意事项

- 评分标准：9-10 改变格局；7-8 直接有帮助；5-6 值得了解；1-4 可略过。  
- 15 个项目中，9-10 分最多 2 个。  
- 技术亮点必须基于事实，不写空话。

## 输出格式

输出为 JSON，结构如下：

```json
{
  "source": "knowledge/raw/latest",
  "skill": "tech-summary",
  "analyzed_at": "YYYY-MM-DDTHH:mm:ssZ",
  "source_file": "knowledge/raw/xxx.json",
  "trends": {
    "themes": ["agent", "rag"],
    "new_concepts": ["concept-a", "concept-b"]
  },
  "items": [
    {
      "name": "owner/repo",
      "url": "https://github.com/owner/repo",
      "summary": "50字以内摘要",
      "highlights": [
        "技术亮点1",
        "技术亮点2"
      ],
      "score": 8,
      "score_reason": "直接有帮助，工程可落地。",
      "tags": ["agent", "workflow"]
    }
  ]
}
```
