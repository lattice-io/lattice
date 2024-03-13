import ReactApexChart from 'react-apexcharts'

type Props = {
  inputs: StaticWorkerData[]
}

export type StaticColorData = {
  name: string
  color: string
}

export type StaticWorkerData = {
  x: string
  y: number
}

const StaticBlockChart: React.FC<Props> = ({ inputs }: Props) => {
  const series = [
    {
      name: 'running worker',
      data: inputs,
    },
  ]

  return (
    <ReactApexChart
      series={series}
      options={{
        chart: {
          type: 'bar',
        },
        dataLabels: {
          enabled: false,
        },
        title: {
          text: 'Active Worker',
        },
        plotOptions: {
          bar: {
            borderRadius: 4,
            horizontal: true,
          },
        },
      }}
      type='bar'
      height={250}
    />
  )
}

export default StaticBlockChart
