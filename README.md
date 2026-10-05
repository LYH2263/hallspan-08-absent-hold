# HallSpan 考场间距排座

在考室网格上按最小曼哈顿距离排座，同试卷套不得四邻相邻，并输出违规与统计。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4900 |
| API | http://localhost:9900 |
| API 文档 | http://localhost:9900/docs |
| Postgres | localhost:5450 |

健康检查：`GET http://localhost:9900/api/health`

## 使用说明

1. 在「考室」「考生」「试卷套」确认基础数据。
2. 打开「排座图」执行间距排座。
3. 在「考生名册」可标记/取消缺考；在「排座图」切换缺考策略：
   - 占格保留（hold）：每个缺考生在占用账留一行占格，该格别人不得坐，占格统计含此人，未排名单不含缺考生。
   - 释放空出（release）：缺考生占用行作废，格子还给后续考生。两策略互斥；策略未配置按释放空出兼容现网。
   - 切换保存失败时，策略字段、占用账、最新方案、统计整体回滚到保存前。
4. 在「违规」查看间距或同卷相邻问题（缺考占格不产生违规说明，缺考名单单独分区）。
5. 在「统计」查看占用（占用账行数）与违规汇总。

## 开发与测试

```bash
docker compose exec api pytest -q
```
