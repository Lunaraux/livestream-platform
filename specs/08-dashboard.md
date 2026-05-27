# 数据大屏服务

## 面向对象
- 管理员大屏：全平台实时数据
- 主播大屏：自己直播间的实时数据

## 管理员大屏接口

### 平台实时概览
GET /api/admin/dashboard/realtime
返回：
- 当前在线用户数
- 当前直播中房间数
- 今日新增用户数
- 今日充值总额（分）
- 今日礼物总额（分）
- 当前弹幕发送速率（条/分钟）

### 平台趋势数据
GET /api/admin/dashboard/trend
- 参数：period（7d/30d/90d）
- 返回：每日用户数、收益、开播次数折线图数据

### 直播间排行
GET /api/admin/dashboard/room-rank
- 当前在线人数 TOP 10 直播间

### 用户增长漏斗
GET /api/admin/dashboard/funnel
- 注册用户 → 消费用户 → 活跃主播

## 主播数据大屏接口

### 本场直播实时数据
GET /api/streamer/dashboard/live
返回：
- 当前在线人数
- 累计观看人数
- 弹幕数量
- 点赞数量
- 礼物收益（分）
- 实时弹幕词云（TOP 20 关键词）

### 历史场次对比
GET /api/streamer/dashboard/history
- 最近10场直播数据对比：时长/峰值人数/收益
