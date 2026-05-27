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
