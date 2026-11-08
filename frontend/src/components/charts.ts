import { BarChart, LineChart, RadarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, RadarComponent, TooltipComponent } from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

use([
  CanvasRenderer,
  RadarChart,
  LineChart,
  BarChart,
  RadarComponent,
  GridComponent,
  TooltipComponent,
  MarkLineComponent,
  LegendComponent,
])

export { default as VChart } from 'vue-echarts'
