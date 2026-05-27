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
