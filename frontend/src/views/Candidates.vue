<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const savingId = ref<number | null>(null)
const errorMsg = ref('')

async function load() { rows.value = await api('/candidates') }
onMounted(load)

async function toggleAbsent(r: any) {
  if (savingId.value !== null) return
  savingId.value = r.id
  errorMsg.value = ''
  const prev = r.absent
  r.absent = !r.absent // 乐观更新；失败回滚
  try {
    const res = await api(`/candidates/${r.id}/absent`, {
      method: 'POST',
      body: JSON.stringify({ absent: !prev }),
    })
    // 保存成功：以服务端同一事务的结果为准（占用账/统计已随新标记重排）
    Object.assign(r, res.candidate)
  } catch (e: any) {
    r.absent = prev
    errorMsg.value = `「${r.name}」缺考标记保存失败，已恢复为保存前状态（占用账与统计未变）`
  } finally {
    savingId.value = null
  }
}
</script>
<template>
  <h1>考生名册</h1>
  <p class="sub">夹板名册样式 · 缺考标记按考室当前策略（占格保留 / 释放空出）落到占用账</p>
  <p v-if="errorMsg" class="hs-error">{{ errorMsg }}</p>
  <div class="hs-clipboard" style="max-width:480px">
    <h2>考生名册 · Clipboard</h2>
    <div v-for="r in rows" :key="r.id ?? JSON.stringify(r)" class="hs-roster-row" :class="{ absent: r.absent }">
      <div>
        <div>{{ r.name }} <span v-if="r.absent" class="hs-absent-badge">缺考</span></div>
        <div class="hs-ticket">{{ r.ticket_no }}</div>
      </div>
      <div style="display:flex;align-items:center;gap:0.5rem">
        <span>卷{{ r.paper_id }} · 室{{ r.hall_id }}</span>
        <button class="btn hs-mini" :disabled="savingId !== null" @click="toggleAbsent(r)">
          {{ r.absent ? '取消缺考' : '标记缺考' }}
        </button>
      </div>
    </div>
  </div>
</template>
