<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
onMounted(async () => { rows.value = await api('/halls') })
function strategyText(r: any) {
  if (r.absent_strategy === 'hold') return '占格保留'
  if (r.absent_strategy === 'release') return '释放空出'
  return '未配置（按释放空出）'
}
</script>
<template>
  <h1>考室</h1>
  <p class="sub">考室网格、最小曼哈顿间距与缺考策略（占格保留 / 释放空出互斥）</p>
  <div class="card">
    <table>
      <thead><tr><th>编码</th><th>名称</th><th>行</th><th>列</th><th>最小间距</th><th>缺考策略</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.code }}</td><td>{{ r.name }}</td><td>{{ r.rows }}</td><td>{{ r.cols }}</td>
          <td>{{ r.min_manhattan }}</td><td>{{ strategyText(r) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
