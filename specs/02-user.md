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
