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
