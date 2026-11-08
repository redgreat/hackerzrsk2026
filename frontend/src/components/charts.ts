import { LineChart, RadarChart } from 'echarts/charts'
import { GridComponent, MarkLineComponent, RadarComponent, TooltipComponent } from 'echarts/components'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

use([CanvasRenderer, RadarChart, LineChart, RadarComponent, GridComponent, TooltipComponent, MarkLineComponent])

export { default as VChart } from 'vue-echarts'
