<script setup lang="ts">
import { computed } from 'vue'
import { VChart } from './charts'

const props = defineProps<{ dimensions: { name: string; score: number }[] }>()

const option = computed(() => ({
  radar: {
    indicator: props.dimensions.map((d) => ({ name: d.name, max: 5 })),
    radius: '62%',
    axisName: { color: '#4e5969', fontSize: 11 },
    splitArea: { areaStyle: { color: ['#f7f9fc', '#fff'] } },
  },
  series: [
    {
      type: 'radar',
      data: [{ value: props.dimensions.map((d) => d.score), name: '得分' }],
      areaStyle: { color: 'rgba(31,111,235,0.25)' },
      lineStyle: { color: '#1f6feb' },
      itemStyle: { color: '#1f6feb' },
    },
  ],
}))
</script>

<template>
  <VChart :option="option" autoresize style="height: 260px" />
</template>
