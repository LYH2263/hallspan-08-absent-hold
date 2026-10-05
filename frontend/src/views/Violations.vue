<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const viols = ref<any[]>([])
const unplaced = ref<any[]>([])
const absent = ref<any[]>([])
const strategy = ref('release')
onMounted(async () => {
  const res = await api('/seating/violations?hall_id=1')
  viols.value = res.violations || []
  unplaced.value = res.unplaced || []
  absent.value = res.absent || []
  strategy.value = res.absent_strategy || 'release'
})
</script>
<template>
  <h1>违规</h1>
  <p class="sub">间距不足或同试卷四邻相邻（缺考占格不产生违规说明）</p>
  <div class="card">
    <table>
      <thead><tr><th>类型</th><th>考生A</th><th>考生B</th><th>说明</th></tr></thead>
      <tbody>
        <tr v-for="(v,i) in viols" :key="i">
          <td>{{ v.kind }}</td><td>{{ v.a_id }}</td><td>{{ v.b_id }}</td><td>{{ v.detail }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!viols.length" class="muted">无违规</p>
  </div>

  <div class="card" v-if="unplaced.length">
    <h3>未排上（可调剂）</h3>
    <p class="muted" style="margin:0 0 0.4rem">缺考生不在此名单，不得当作可调剂未排。</p>
    <div v-for="u in unplaced" :key="u.id">{{ u.name }}（{{ u.ticket_no }}）</div>
  </div>

  <div class="card" v-if="absent.length">
    <h3>缺考名单</h3>
    <p class="muted" style="margin:0 0 0.4rem">
      当前策略：{{ strategy === 'hold' ? '占格保留' : '释放空出（未配置时按此兼容现网）' }}
    </p>
    <!-- 缺考占用说明单独成句，绝不与间距违规说明并句 -->
    <div v-for="a in absent" :key="a.id" class="hs-absent-row">
      {{ a.name }}（{{ a.ticket_no }}）：
      <template v-if="strategy === 'hold' && a.held">占用账保留一行占格，该格别人不得坐，占格统计含此人。</template>
      <template v-else>占用行已作废，格子已还给后续考生。</template>
    </div>
  </div>
</template>
