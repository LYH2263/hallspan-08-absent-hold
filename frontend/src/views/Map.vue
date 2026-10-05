<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>(null)
const candidates = ref<any[]>([])
const violKeys = ref<Set<string>>(new Set())
const saving = ref(false)
const errorMsg = ref('')

function applyPlan(plan: any) {
  // 排座图、占用账、统计、未排/缺考名单全部取自这同一份方案
  data.value = plan
  const keys = new Set<string>()
  for (const x of plan.violations || []) {
    if (x.a_id != null) keys.add(String(x.a_id))
    if (x.b_id != null) keys.add(String(x.b_id))
  }
  violKeys.value = keys
}

async function run() {
  errorMsg.value = ''
  try {
    applyPlan(await api('/seating/run?hall_id=1', { method: 'POST' }))
  } catch (e: any) {
    errorMsg.value = '重新排座失败，仍展示保存前结果'
  }
}

async function switchStrategy(strategy: string) {
  if (!data.value || data.value.absent_strategy === strategy || saving.value) return
  saving.value = true
  errorMsg.value = ''
  // 先记住旧方案：保存失败时整体回滚，界面继续展示旧策略占格
  const prev = data.value
  try {
    const plan = await api('/halls/1/absent-strategy', {
      method: 'POST',
      body: JSON.stringify({ absent_strategy: strategy }),
    })
    applyPlan(plan) // 占用账与图按新策略整体重写
  } catch (e: any) {
    data.value = prev
    errorMsg.value = '策略保存失败，已恢复到保存前策略、占用账与统计'
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  candidates.value = await api('/candidates')
  await run()
})

const gridStyle = computed(() => data.value ? ({ gridTemplateColumns: `repeat(${data.value.cols}, 72px)` }) : {})
const cells = computed(() => {
  if (!data.value) return []
  const map = new Map<string, any>()
  // 占用账是唯一占格依据：账上有的格别人不得坐，账上没有的格即为空（release 时空出格可被他人使用）
  for (const a of data.value.assignments || []) map.set(a.row + ',' + a.col, a)
  const out: any[] = []
  for (let r = 0; r < data.value.rows; r++) {
    for (let c = 0; c < data.value.cols; c++) {
      out.push(map.get(r + ',' + c) || { empty: true, row: r, col: c })
    }
  }
  return out
})
function isHeld(cell: any) { return !cell.empty && cell.status === 'reserved_absent' }
function isViol(cell: any) {
  if (cell.empty || isHeld(cell)) return false
  const id = cell.candidate_id ?? cell.id
  return id != null && violKeys.value.has(String(id))
}
function paperClass(pid: number) { return pid % 2 === 0 ? 'b' : 'a' }
</script>
<template>
  <h1>考场课桌网格</h1>
  <p class="sub">课桌网格为主视图 · 左侧考生名册夹板 · 违规课桌高亮 · 缺考占格与释放空出互斥</p>
  <div class="hs-toolbar">
    <button class="btn" @click="run" :disabled="saving">重新排座</button>
    <span class="hs-strat-label">缺考策略：</span>
    <button
      class="btn hs-strat" :class="{ active: data?.absent_strategy === 'hold' }"
      :disabled="saving" @click="switchStrategy('hold')"
    >占格保留</button>
    <button
      class="btn hs-strat" :class="{ active: data?.absent_strategy === 'release' }"
      :disabled="saving" @click="switchStrategy('release')"
    >释放空出</button>
    <span v-if="saving" class="muted">保存中…</span>
  </div>
  <p v-if="errorMsg" class="hs-error">{{ errorMsg }}</p>
  <p class="sub" v-if="data" style="margin-top:0.5rem">
    当前：<b>{{ data.absent_strategy === 'hold' ? '占格保留（缺考留占格行，他人不得坐，占格统计含此人）' : '释放空出（缺考占用行作废，格子还给后续考生）' }}</b>
    · 占格 {{ data.stats.occupied }} / 容量 {{ data.stats.capacity }}（其中缺考占格 {{ data.stats.held_absent }}）
  </p>
  <div class="hs-classroom" style="margin-top:0.4rem">
    <aside class="hs-clipboard">
      <h2>考生名册</h2>
      <div v-for="c in candidates" :key="c.id" class="hs-roster-row" :class="{ absent: c.absent }">
        <div>
          <div>{{ c.name }} <span v-if="c.absent" class="hs-absent-badge">缺考</span></div>
          <div class="hs-ticket">{{ c.ticket_no }}</div>
        </div>
        <div>卷{{ c.paper_id }}</div>
      </div>
    </aside>
    <div class="hs-desk-stage" v-if="data">
      <div class="hs-grid-board" :style="gridStyle">
        <div
          v-for="(cell,i) in cells" :key="i"
          class="hs-desk"
          :class="{ empty: cell.empty, 'hs-viol': isViol(cell), 'hs-absent-hold': isHeld(cell) }"
        >
          <template v-if="isHeld(cell)">
            <span class="hs-hold-ribbon">缺考占格</span>
            <div>{{ cell.name }}</div>
          </template>
          <template v-else-if="!cell.empty">
            <span class="hs-paper-tag" :class="paperClass(cell.paper_id)">卷{{ cell.paper_id }}</span>
            <div>{{ cell.name }}</div>
          </template>
          <template v-else>·</template>
        </div>
      </div>
    </div>
  </div>
</template>
