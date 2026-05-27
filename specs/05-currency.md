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
