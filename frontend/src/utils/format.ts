import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)

/** Convert UTC ISO string to Asia/Shanghai formatted string */
export function formatTime(utcStr: string | null, format = 'YYYY-MM-DD HH:mm:ss'): string {
  if (!utcStr) return '-'
  return dayjs.utc(utcStr).tz('Asia/Shanghai').format(format)
}

/** Convert fen (分) to yuan (元) */
export function fenToYuan(fen: number): string {
  return (fen / 100).toFixed(2)
}

/** Format duration in seconds to human readable */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}秒`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}时${m}分${s}秒`
  if (m > 0) return `${m}分${s}秒`
  return `${s}秒`
}

/** Room category labels */
export const categoryLabels: Record<string, string> = {
  game: '游戏',
  music: '音乐',
  dance: '舞蹈',
  chat: '聊天',
  talent: '才艺',
  outdoor: '户外',
  education: '教育',
  other: '其他',
}

/** Room status labels */
export const statusLabels: Record<string, string> = {
  idle: '待机中',
  live: '直播中',
  ended: '已结束',
  banned: '已封禁',
}

/** Role labels */
export const roleLabels: Record<string, string> = {
  audience: '观众',
  streamer: '主播',
  admin: '管理员',
}
