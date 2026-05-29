import { onUnmounted } from 'vue'
import { useWebSocketStore } from '@/stores/websocket'

export function useRoomWebSocket(roomId: number) {
  const wsStore = useWebSocketStore()

  wsStore.connect(roomId)

  onUnmounted(() => {
    wsStore.disconnect()
  })

  function onDanmaku(handler: (data: any) => void) {
    wsStore.on('danmaku', handler)
  }

  function onLike(handler: (data: any) => void) {
    wsStore.on('like', handler)
  }

  function onViewerUpdate(handler: (data: any) => void) {
    wsStore.on('viewer_update', handler)
  }

  function onGift(handler: (data: any) => void) {
    wsStore.on('gift', handler)
  }

  function offDanmaku(handler: (data: any) => void) {
    wsStore.off('danmaku', handler)
  }

  function offLike(handler: (data: any) => void) {
    wsStore.off('like', handler)
  }

  function offViewerUpdate(handler: (data: any) => void) {
    wsStore.off('viewer_update', handler)
  }

  function offGift(handler: (data: any) => void) {
    wsStore.off('gift', handler)
  }

  // Ping to keep alive
  const pingInterval = setInterval(() => {
    wsStore.send('ping')
  }, 30000)

  onUnmounted(() => {
    clearInterval(pingInterval)
  })

  return {
    connected: wsStore.connected,
    send: wsStore.send,
    onDanmaku,
    onLike,
    onViewerUpdate,
    onGift,
    offDanmaku,
    offLike,
    offViewerUpdate,
    offGift,
  }
}
