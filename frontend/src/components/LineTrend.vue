<script setup lang="ts">
import { computed } from 'vue'
import { VChart } from './charts'

const props = withDefaults(
  defineProps<{ values: number[]; labels?: string[]; max?: number; markLine?: number | null; height?: number }>(),
  { max: 100, markLine: null, height: 200 },
)

const option = computed(() => ({
  grid: { left: 36, right: 16, top: 20, bottom: 28 },
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: props.labels ?? props.values.map((_, i) => String(i)), boundaryGap: false },
  yAxis: { type: 'value', min: 0, max: props.max },
  series: [
    {
      type: 'line',
      data: props.values,
      smooth: true,
      symbolSize: 7,
      lineStyle: { color: '#1f6feb', width: 3 },
      itemStyle: { color: '#1f6feb' },
      areaStyle: { color: 'rgba(31,111,235,0.12)' },
      markLine:
        props.markLine == null
          ? undefined
          : { symbol: 'none', data: [{ yAxis: props.markLine }], lineStyle: { color: '#00b42a', type: 'dashed' } },
    },
  ],
}))
</script>

<template>
  <VChart :option="option" autoresize :style="{ height: `${height}px` }" />
</template>
