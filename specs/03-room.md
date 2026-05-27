# 直播间服务

## 直播间状态机
```
待机(idle) → 直播中(live) → 已结束(ended)
直播中(live) → 已封禁(banned)
已封禁(banned) → 直播中(live)  （管理员解封后可重新开播）
```

## 接口列表

### 创建直播间
POST /api/rooms
- 需要主播权限且已通过认证
- 参数：title（标题）, description, category（分类）, cover_url
- 每个主播只能有一个直播间

### 开始直播
POST /api/rooms/{room_id}/start
- 仅房间主播可操作
- 记录开播时间
- 推送通知给所有关注该主播的观众（写入消息队列）

### 结束直播
POST /api/rooms/{room_id}/end
- 仅房间主播可操作
- 记录本场直播时长、峰值在线人数、总收益
- 触发结算流程（见 06-settlement.md）

### 获取直播间详情
GET /api/rooms/{room_id}
- 返回直播间信息、主播信息、当前在线人数、直播状态

### 直播间列表
GET /api/rooms
- 支持按分类筛选、按在线人数排序、按开播时间排序
- 只返回直播中的房间
- 支持分页

### 推荐直播间
GET /api/rooms/recommended
- 返回在线人数最多的 10 个直播间

### 搜索直播间
GET /api/rooms/search?q=关键词
- 按标题搜索

### 更新直播间信息
PUT /api/rooms/{room_id}
- 仅房间主播可操作

### 管理员：封禁直播间
POST /api/admin/rooms/{room_id}/ban
- 参数：reason

### 管理员：解封直播间
POST /api/admin/rooms/{room_id}/unban

## 直播间分类
- 游戏、音乐、舞蹈、聊天、才艺、户外、教育、其他

## 数据模型
直播间核心字段：
- id, streamer_id, title, description, category, cover_url
- status（idle/live/ended/banned）
- current_viewers（当前在线人数，存 Redis）
- peak_viewers（本场峰值人数）
- total_sessions（总开播次数）
- started_at, ended_at
- created_at, updated_at
