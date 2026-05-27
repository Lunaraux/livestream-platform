#!/bin/bash
mkdir -p ~/projects/livestream-platform/specs
cd ~/projects/livestream-platform

# ============================================================
# SPEC.md 总纲
# ============================================================
cat > SPEC.md << 'EOF'
# 直播间管理平台 — 系统总纲

## 项目定位
一个支持多主播、多直播间的实时互动直播管理平台。
观众可以进入直播间观看、发弹幕、送礼物、打赏主播。
主播可以管理直播间、查看收益。
管理员可以监控全平台数据。

## 技术栈
- 后端：Python 3.11 + FastAPI + PostgreSQL + Redis
- 前端：Vue 3 + Vite + Element Plus（中文界面）
- 实时通信：WebSocket
- 部署：Docker Compose（一键启动）

## 全局约定
- 所有货币金额单位：分（整数），禁止使用浮点数
- 所有时间：服务器 UTC 时间，前端显示转换为 Asia/Shanghai
- 所有接口返回统一格式，参见 specs/00-global.md
- 错误码规范参见 specs/00-global.md

## 模块依赖顺序（按此顺序实现）
1. 00-global    全局定义（先读，贯穿所有模块）
2. 01-auth      认证授权（其他所有模块依赖）
3. 02-user      用户服务（主播/观众/管理员）
4. 03-room      直播间服务
5. 04-interaction 互动服务（弹幕/点赞/礼物）
6. 05-currency  虚拟货币（充值/消费）
7. 06-settlement 结算服务（收益/分成/提现）
8. 07-realtime  WebSocket 实时服务
9. 08-dashboard 数据大屏
10. 09-frontend  Vue 前端

## 角色体系
| 角色 | 说明 |
|------|------|
| 游客 | 未登录，只能浏览直播间列表 |
| 观众 | 登录用户，可以进入直播间互动 |
| 主播 | 可以创建和管理直播间 |
| 管理员 | 平台管理，封禁/数据监控 |

## 项目目录结构
```
livestream-platform/
├── backend/
│   ├── app/
│   │   ├── api/          # 路由层
│   │   ├── models/       # 数据库模型
│   │   ├── schemas/      # Pydantic 模型
│   │   ├── services/     # 业务逻辑层
│   │   ├── core/         # 配置/安全/依赖
│   │   └── websocket/    # WebSocket 处理
│   ├── tests/            # 测试
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── views/        # 页面
│   │   ├── components/   # 组件
│   │   ├── stores/       # Pinia 状态管理
│   │   └── api/          # 接口调用
│   └── package.json
├── docker-compose.yml
└── README.md
```
EOF

# ============================================================
# 00-global.md
# ============================================================
cat > specs/00-global.md << 'EOF'
# 全局定义

## 统一响应格式
所有接口必须返回以下格式：
```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```
成功时 code=0，失败时 code 为对应错误码。

## 错误码规范
| 错误码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1001 | 参数错误 |
| 1002 | 未登录 |
| 1003 | 无权限 |
| 1004 | 资源不存在 |
| 2001 | 用户名已存在 |
| 2002 | 密码错误 |
| 2003 | 账号已封禁 |
| 3001 | 直播间不存在 |
| 3002 | 直播间已关闭 |
| 3003 | 直播间已封禁 |
| 4001 | 余额不足 |
| 4002 | 充值金额非法 |
| 4003 | 礼物不存在 |
| 5001 | 提现金额不足最低限额 |
| 5002 | 提现申请处理中，请勿重复提交 |

## 货币约定
- 所有金额字段类型为 INTEGER，单位为分
- 字段命名规范：amount_fen（如 price_fen, balance_fen）
- 严禁使用 FLOAT/DECIMAL 存储金额
- 平台分成比例存储为整数百分比（如 30 表示 30%）

## 时间约定
- 数据库存储：UTC 时间戳（INTEGER）
- 接口传入：ISO 8601 字符串
- 接口返回：ISO 8601 字符串（UTC）
- 前端显示：转换为 Asia/Shanghai

## 分页约定
所有列表接口支持分页：
- 请求参数：page（从1开始），page_size（默认20，最大100）
- 返回结构：
```json
{
  "items": [],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

## 数据库约定
- 所有表必须有 id（BIGSERIAL PRIMARY KEY）
- 所有表必须有 created_at、updated_at（UTC 时间戳）
- 软删除字段：deleted_at（NULL 表示未删除）
- 索引：所有外键字段必须建索引
EOF

# ============================================================
# 01-auth.md
# ============================================================
cat > specs/01-auth.md << 'EOF'
# 认证授权服务

## 功能概述
基于 JWT 的认证系统，支持注册、登录、刷新 Token、登出。

## 接口列表

### 注册
POST /api/auth/register
请求：
- username: 用户名（4-20位，字母数字下划线）
- password: 密码（8-20位，必须包含字母和数字）
- nickname: 昵称（2-20位）
- role: 注册角色（audience=观众，streamer=主播）

业务规则：
- 用户名全局唯一，重复返回错误码 2001
- 密码必须 bcrypt 加密存储，禁止明文
- 注册后自动创建用户钱包，初始余额为 0

### 登录
POST /api/auth/login
请求：
- username
- password
返回：
- access_token（有效期 2 小时）
- refresh_token（有效期 7 天）
- user_info（用户基本信息）

业务规则：
- 连续登录失败 5 次，锁定账号 30 分钟
- 登录成功记录登录时间和 IP

### 刷新 Token
POST /api/auth/refresh
请求：refresh_token
返回：新的 access_token

### 登出
POST /api/auth/logout
- 将 refresh_token 加入黑名单（存 Redis，TTL=7天）

### 获取当前用户信息
GET /api/auth/me
- 需要 Authorization: Bearer <token>
- 返回当前登录用户完整信息

## 安全要求
- 所有需要登录的接口必须验证 JWT
- Token 存储在 Redis 黑名单中实现主动失效
- 密码修改后所有旧 Token 立即失效
EOF

# ============================================================
# 02-user.md
# ============================================================
cat > specs/02-user.md << 'EOF'
# 用户服务

## 用户等级体系
观众根据累计消费金额自动升级：
| 等级 | 名称 | 累计消费（分） | 专属特权 |
|------|------|---------------|---------|
| 1 | 普通观众 | 0 | 无 |
| 2 | 铁牌粉丝 | 10000 | 弹幕颜色变灰 |
| 3 | 铜牌粉丝 | 50000 | 弹幕颜色变铜 |
| 4 | 银牌粉丝 | 200000 | 弹幕颜色变银，进场特效 |
| 5 | 金牌粉丝 | 500000 | 弹幕颜色变金，专属徽章 |
| 6 | 钻石粉丝 | 2000000 | 弹幕颜色变钻，置顶弹幕特权 |

## 主播认证
- 主播需要填写真实姓名、身份证号（脱敏存储）
- 管理员审核通过后才能开播
- 主播有独立的收益账户

## 接口列表

### 获取用户主页
GET /api/users/{user_id}
- 返回公开信息（昵称/等级/粉丝数/直播间）

### 更新个人资料
PUT /api/users/me
- 可修改：昵称、头像URL、个人简介

### 修改密码
POST /api/users/me/password
- 需要验证旧密码

### 关注/取消关注主播
POST /api/users/{streamer_id}/follow
DELETE /api/users/{streamer_id}/follow

### 获取关注列表
GET /api/users/me/following
- 返回我关注的主播列表，包含直播状态

### 获取粉丝列表
GET /api/users/me/followers
- 仅主播可查看自己的粉丝列表

### 管理员：封禁用户
POST /api/admin/users/{user_id}/ban
- 需要管理员权限
- 参数：reason（封禁原因），duration_hours（封禁时长，0=永久）

### 管理员：解封用户
POST /api/admin/users/{user_id}/unban

### 管理员：审核主播认证
POST /api/admin/streamers/{user_id}/verify
- 参数：approved（true/false），reject_reason

## 数据模型
用户表核心字段：
- id, username, password_hash, nickname, avatar_url
- role（audience/streamer/admin）
- level（1-6，观众等级）
- total_consumed_fen（累计消费金额，用于等级计算）
- is_banned, ban_until, ban_reason
- streamer_verified（主播是否已认证）
- created_at, updated_at
EOF

# ============================================================
# 03-room.md
# ============================================================
cat > specs/03-room.md << 'EOF'
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
EOF

# ============================================================
# 04-interaction.md
# ============================================================
cat > specs/04-interaction.md << 'EOF'
# 互动服务（弹幕/点赞/礼物）

## 弹幕系统

### 发送弹幕
POST /api/rooms/{room_id}/danmaku
- 需要登录
- 参数：content（内容，最长100字）, color（颜色，受等级限制）
- 弹幕颜色规则：
  - 等级1-3：只能发白色弹幕
  - 等级4：可选灰/白
  - 等级5：可选铜/灰/白
  - 等级6：可选金/银/铜/灰/白
  - 钻石等级：可选任意颜色，支持置顶（duration_seconds 最长30秒）
- 直播间封禁状态禁止发弹幕
- 用户封禁状态禁止发弹幕
- 弹幕内容违禁词过滤（维护违禁词表）
- 同一用户同一直播间发弹幕频率限制：每5秒最多3条（Redis 限流）

### 获取历史弹幕
GET /api/rooms/{room_id}/danmaku
- 返回最近 100 条弹幕

### 点赞
POST /api/rooms/{room_id}/like
- 需要登录
- 每个用户每场直播最多点赞 1000 次（存 Redis）
- 每次点赞 +1，前端显示累计点赞数

### 礼物系统

#### 礼物列表
平台预设礼物，管理员维护：
| 礼物名称 | 价格（分） | 展示效果 |
|---------|----------|---------|
| 小星星 | 100 | 普通动画 |
| 爱心 | 500 | 普通动画 |
| 火箭 | 5000 | 全屏特效 |
| 超级星舰 | 50000 | 全屏特效+公告 |
| 守护船票 | 198000 | 月度守护特效 |

#### 获取礼物列表
GET /api/gifts
- 返回所有可用礼物及价格

#### 赠送礼物
POST /api/rooms/{room_id}/gifts
- 需要登录
- 参数：gift_id, quantity（数量，1-99）
- 业务规则：
  - 检查用户余额是否充足（余额不足返回 4001）
  - 扣除用户余额（原子操作）
  - 增加主播待结算收益
  - 记录礼物流水
  - 触发实时推送（见 07-realtime.md）
  - 超级星舰/守护船票触发全直播间公告

#### 礼物排行榜
GET /api/rooms/{room_id}/gift-rank
- 本场直播礼物价值 TOP 10 用户

## 违禁词管理（管理员）
GET /api/admin/forbidden-words
POST /api/admin/forbidden-words
DELETE /api/admin/forbidden-words/{id}
EOF

# ============================================================
# 05-currency.md
# ============================================================
cat > specs/05-currency.md << 'EOF'
# 虚拟货币服务

## 货币体系
- 平台虚拟货币：金币（单位：分）
- 充值：人民币 → 金币（模拟支付，不接真实支付网关）
- 消费：送礼物、购买特权
- 提现：主播收益 → 模拟银行转账

## 充值规则
| 档位 | 充值金额（分） | 赠送金额（分） |
|------|-------------|-------------|
| 1 | 600 | 0 |
| 2 | 3000 | 150 |
| 3 | 6000 | 600 |
| 4 | 30000 | 6000 |
| 5 | 60000 | 18000 |
| 6 | 300000 | 120000 |

## 接口列表

### 查询余额
GET /api/wallet/balance
- 返回：可用余额（balance_fen）、冻结余额（frozen_fen）

### 充值（模拟支付）
POST /api/wallet/recharge
- 参数：tier（档位 1-6）
- 模拟支付流程：
  1. 创建充值订单（pending 状态）
  2. 返回模拟支付链接
  3. 客户端访问支付链接后自动成功
  4. 到账金额 = 充值金额 + 赠送金额
- 幂等设计：同一订单号只能充值一次

### 模拟支付回调
POST /api/wallet/recharge/{order_id}/pay
- 模拟支付网关回调
- 验证订单状态为 pending，更新为 paid
- 原子操作增加用户余额
- 记录流水

### 充值记录
GET /api/wallet/recharge-history
- 支持分页，返回充值记录列表

### 消费流水
GET /api/wallet/transactions
- 支持分页，按类型筛选（充值/送礼/购买特权）
- 返回所有金币变动记录

## 数据模型

### 钱包表（wallets）
- user_id, balance_fen, frozen_fen
- 必须有唯一索引：user_id

### 流水表（transactions）
- id, user_id, type（recharge/gift/privilege）
- amount_fen（正数=收入，负数=支出）
- balance_before_fen, balance_after_fen
- ref_id（关联业务ID）, description
- created_at

### 充值订单表（recharge_orders）
- id, order_no（唯一），user_id
- tier, recharge_fen, bonus_fen, total_fen
- status（pending/paid/failed）
- paid_at, created_at

## 安全要求
- 所有余额变更必须在数据库事务中完成
- 余额不能为负数（数据库层面加 CHECK 约束）
- 流水必须记录变更前后余额，用于对账
EOF

# ============================================================
# 06-settlement.md
# ============================================================
cat > specs/06-settlement.md << 'EOF'
# 结算服务

## 收益分成规则
- 平台抽成：30%（存储为整数 30，不用浮点）
- 主播到手：70%
- 计算方式：主播收益 = floor(礼物总价值 * 70 / 100)（整数除法，向下取整）
- 平台收益 = 礼物总价值 - 主播收益

## 结算触发时机
1. 主播手动结束直播时，触发本场结算
2. 每天凌晨 2 点，自动结算所有未结算直播场次

## 结算流程
1. 汇总本场所有礼物收入
2. 按分成规则计算主播应得金额
3. 将金额从"待结算"转入"可提现"
4. 生成结算账单

## 接口列表

### 主播收益概览
GET /api/streamer/earnings
- 返回：今日收益、本月收益、累计收益、可提现余额、待结算余额

### 收益明细
GET /api/streamer/earnings/detail
- 支持按日期范围筛选
- 返回每场直播的收益明细

### 申请提现
POST /api/streamer/withdraw
- 参数：amount_fen（提现金额）
- 规则：
  - 最低提现金额：10000分（100元）
  - 可提现余额必须充足
  - 同一主播同时只能有一笔处理中的提现申请（返回错误码 5002）
  - 提现申请创建后冻结对应金额

### 提现记录
GET /api/streamer/withdraw-history

### 管理员：处理提现申请
POST /api/admin/withdraw/{id}/approve
POST /api/admin/withdraw/{id}/reject
- approve：模拟打款，释放冻结金额，扣减可提现余额，记录流水
- reject：释放冻结金额，退回可提现余额，填写拒绝原因

### 管理员：平台收益统计
GET /api/admin/platform/revenue
- 返回平台每日/月收益数据

## 数据模型

### 主播收益账户（streamer_wallets）
- streamer_id
- pending_fen（待结算）
- available_fen（可提现）
- frozen_fen（提现冻结中）
- total_earned_fen（历史累计）

### 结算账单（settlement_bills）
- id, room_id, streamer_id, session_id
- total_gift_fen（本场礼物总额）
- platform_fee_fen（平台抽成）
- streamer_earn_fen（主播到手）
- settled_at

### 提现申请（withdraw_requests）
- id, streamer_id, amount_fen
- status（pending/approved/rejected）
- reject_reason, processed_at
EOF

# ============================================================
# 07-realtime.md
# ============================================================
cat > specs/07-realtime.md << 'EOF'
# 实时服务（WebSocket）

## 连接端点
WS /ws/rooms/{room_id}
- 连接时需要携带 token（query param: ?token=xxx）
- 游客（未登录）可以连接但只能接收消息，不能发送

## 消息协议
所有消息为 JSON 格式：
```json
{
  "type": "消息类型",
  "data": {}
}
```

## 客户端 → 服务端消息类型
| type | 说明 | data |
|------|------|------|
| ping | 心跳 | {} |
| danmaku | 发送弹幕 | {content, color} |
| like | 点赞 | {} |

## 服务端 → 客户端消息类型
| type | 说明 | data |
|------|------|------|
| pong | 心跳响应 | {} |
| danmaku | 弹幕广播 | {user_id, nickname, level, content, color} |
| like | 点赞广播 | {count（累计）} |
| gift | 礼物广播 | {user_id, nickname, gift_name, quantity, total_fen} |
| gift_special | 大额礼物全屏 | {同上，含特效类型} |
| viewer_update | 在线人数变化 | {count} |
| room_banned | 直播间被封禁 | {reason} |
| announcement | 系统公告 | {content} |
| user_enter | 用户进入（高等级） | {nickname, level}（仅5级以上触发） |

## 在线人数管理
- 用户连接：Redis INCR room:{id}:viewers
- 用户断开：Redis DECR room:{id}:viewers
- 每30秒广播一次在线人数
- 连接超时：90秒无心跳自动断开

## 频率限制
- 弹幕：每用户每5秒最多3条（Redis 滑动窗口）
- 点赞：每用户每场最多1000次
- 违规操作直接断开连接
EOF

# ============================================================
# 08-dashboard.md
# ============================================================
cat > specs/08-dashboard.md << 'EOF'
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
EOF

# ============================================================
# 09-frontend.md
# ============================================================
cat > specs/09-frontend.md << 'EOF'
# 前端规范（Vue 3 + Element Plus）

## 技术栈
- Vue 3 + Composition API
- Vite 构建
- Element Plus 组件库（中文语言包）
- Pinia 状态管理
- Vue Router 路由
- Axios 请求封装
- ECharts 图表

## 页面列表

### 公开页面（无需登录）
| 路径 | 页面 |
|------|------|
| / | 首页（直播间列表+推荐） |
| /login | 登录页 |
| /register | 注册页 |
| /rooms/:id | 直播间页面（可观看，不可互动） |

### 用户页面（需要登录）
| 路径 | 页面 |
|------|------|
| /rooms/:id | 直播间页面（可互动） |
| /wallet | 我的钱包（余额/充值/流水） |
| /following | 我的关注 |
| /profile | 个人资料 |

### 主播页面（需要主播权限）
| 路径 | 页面 |
|------|------|
| /streamer/room | 我的直播间管理 |
| /streamer/live | 开播控制台 |
| /streamer/earnings | 收益中心 |
| /streamer/dashboard | 数据大屏 |

### 管理员页面（需要管理员权限）
| 路径 | 页面 |
|------|------|
| /admin/dashboard | 平台数据大屏 |
| /admin/users | 用户管理 |
| /admin/rooms | 直播间管理 |
| /admin/withdraw | 提现审核 |
| /admin/gifts | 礼物管理 |

## 直播间页面核心布局
```
┌─────────────────────────────────────┐
│  顶部导航栏                           │
├───────────────────┬─────────────────┤
│                   │  主播信息         │
│  模拟播放器区域     │  在线人数         │
│  （显示封面图）     ├─────────────────┤
│                   │  弹幕列表         │
│                   │  （实时滚动）     │
├───────────────────┼─────────────────┤
│  礼物栏 + 点赞按钮  │  弹幕输入框      │
└───────────────────┴─────────────────┘
```

## 全局要求
- 所有金额显示：前端将分转换为元（除以100），保留2位小数
- 所有时间显示：转换为 Asia/Shanghai 时区
- 未登录访问需登录的页面，重定向到 /login
- API 请求统一错误处理，code≠0 时 Toast 提示 message
- WebSocket 断线自动重连（最多3次，间隔递增）
- 响应式设计，支持 PC 和移动端

## Docker 部署
- 前端 build 后由 Nginx 托管
- 后端 FastAPI 用 uvicorn 运行
- docker-compose.yml 一键启动所有服务
EOF

echo "✅ 所有 SPEC 文件生成完成！"
echo ""
echo "文件结构："
find ~/projects/livestream-platform -type f | sort