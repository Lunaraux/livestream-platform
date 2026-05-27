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
