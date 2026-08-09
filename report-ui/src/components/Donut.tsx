import { Cell, Pie, PieChart, Tooltip } from 'recharts'

type Slice = { name: string; value: number; color: string }

export function Donut({ data, size = 150 }: { data: Slice[]; size?: number }) {
  if (!data.length) return <div className="empty">No data</div>
  const inner = Math.round(size * 0.27)
  const outer = Math.round(size * 0.43)

  return (
    <PieChart width={size} height={size}>
      <Pie
        data={data}
        dataKey="value"
        nameKey="name"
        cx={size / 2}
        cy={size / 2}
        innerRadius={inner}
        outerRadius={outer}
        paddingAngle={2}
        isAnimationActive={false}
      >
        {data.map((d) => (
          <Cell key={d.name} fill={d.color} />
        ))}
      </Pie>
      <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
    </PieChart>
  )
}
