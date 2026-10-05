<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const s = ref<any>({})
onMounted(async () => { s.value = await api('/seating/stats?hall_id=1') })
</script>
<template>
  <h1>统计</h1>
  <p class="sub">排座占用与违规汇总 · 占格数=占用账行数（占格保留时含缺考占格）</p>
  <div class="card" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem">
    <div><div class="muted">占格数（占用账）</div><div class="stat">{{ s.occupied }}</div></div>
    <div><div class="muted">实际就座</div><div class="stat">{{ s.seated }}</div></div>
    <div><div class="muted">其中缺考占格</div><div class="stat">{{ s.held_absent }}</div></div>
    <div><div class="muted">缺考人数</div><div class="stat">{{ s.absent }}</div></div>
    <div><div class="muted">未排上</div><div class="stat">{{ s.unplaced }}</div></div>
    <div><div class="muted">违规数</div><div class="stat">{{ s.violations }}</div></div>
    <div><div class="muted">座位容量</div><div class="stat">{{ s.capacity }}</div></div>
  </div>
  <p class="muted" style="font-size:0.8rem">
    占格保留：占格数含缺考生、该格他人不得坐；释放空出：缺考无占用行、格子还给后续考生。两种策略只生效一种。
  </p>
</template>
