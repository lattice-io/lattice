import ReactApexChart from 'react-apexcharts'
import {colors} from '../../../config/apis'

type Props = {
  series?: any
}

export type WorkerNum = {
  time: number
  value: number
}

export type WorkerData = {
  name: string
  data: Array<{
    x: number
    y: number
  }>
}

const TimeSeriesChart: React.FC<Props> = ({ series }: Props) => {
  const options: ApexCharts.ApexOptions = {
    chart: {
      type: 'area',
      height: 350,
      animations: {
        enabled: true,
        easing: 'linear',
        dynamicAnimation: {
          speed: 2000,
        },
      },
    },
    colors: colors,
    dataLabels: {
      enabled: false,
    },
    stroke: {
      curve: 'smooth',
    },
    yaxis: {
      forceNiceScale: true,
      min: 0
    },
    xaxis: {
      title: {
        text: 'Time (UTC)',
        offsetX: 0,
        offsetY: 0,
        style: {
          color: undefined,
          fontSize: '12px',
          fontFamily: 'Helvetica, Arial, sans-serif',
          fontWeight: 600,
          cssClass: 'apexcharts-yaxis-title',
        },
      },
      type: 'datetime',
      range: 3600000, // 1 hour
      labels: {
        datetimeFormatter: {
          year: 'yyyy',
          month: "MMM 'yy",
          day: 'dd MMM',
          hour: 'HH:mm',
        },
        style: {
          fontSize: '14px',
        },
      },
    },
    legend: {
      position: 'top',
      horizontalAlign: 'left',
      showForSingleSeries: true,
    },
    title: {
      text: 'Active Worker (Timeseries)',
    },
    tooltip: {
      enabled: false,
    },
    fill: {
      type: 'gradient',
    },
    markers: {
      size: 0,
    },
    grid: {
      borderColor: '#f1f1f1',
    },
  }

  return (
    <ReactApexChart
      series={series}
      options={options}
      type='area'
      height={250}
    />
  )
}

export default TimeSeriesChart
