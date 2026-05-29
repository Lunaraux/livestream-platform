import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { WsMessage } from '@/types'

export const useWebSocketStore = defineStore('websocket', () => {
  const ws = ref<WebSocket | null>(null)
  const connected = ref(false)
  const reconnectCount = ref(0)
  const maxReconnects = 3
  const messageHandlers = new Map<string, Set<(data: any) => void>>()

  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  function connect(roomId: number) {
    const token = localStorage.getItem('access_token') || ''
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.host
    const url = `${protocol}://${host}/ws/rooms/${roomId}?token=${token}`

    if (ws.value) {
      ws.value.close()
    }

    const socket = new WebSocket(url)
    ws.value = socket

    socket.onopen = () => {
      connected.value = true
      reconnectCount.value = 0
    }

    socket.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data)
        const handlers = messageHandlers.get(msg.type)
        if (handlers) {
          handlers.forEach((fn) => fn(msg.data))
        }
      } catch {
        // Ignore parse errors
      }
    }

    socket.onclose = () => {
      connected.value = false
      ws.value = null
      if (reconnectCount.value < maxReconnects) {
        const delay = Math.pow(2, reconnectCount.value) * 1000
        reconnectTimer = setTimeout(() => {
          reconnectCount.value++
          connect(roomId)
        }, delay)
      }
    }

    socket.onerror = () => {
      // onclose will handle reconnect
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    reconnectCount.value = 0
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    connected.value = false
  }

  function send(type: string, data: any = {}) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({ type, data }))
    }
  }

  function on(type: string, handler: (data: any) => void) {
    if (!messageHandlers.has(type)) {
      messageHandlers.set(type, new Set())
    }
    messageHandlers.get(type)!.add(handler)
  }

  function off(type: string, handler: (data: any) => void) {
    const handlers = messageHandlers.get(type)
    if (handlers) {
      handlers.delete(handler)
    }
  }

  return { ws, connected, connect, disconnect, send, on, off }
})
