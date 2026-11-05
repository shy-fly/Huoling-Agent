type Point = { phase: number; value: number };
const colors = ["#196d91", "#a04e27"];

export default function FanChart({ series, pdfUrl }: { series: [Point[], Point[]]; pdfUrl: string }) {
    const ceiling = Math.ceil(Math.max(...series.flat().map(point => point.value)) / 100) * 100;
    const x = (phase: number) => 48 + phase * 44;
    const y = (value: number) => 202 - value / ceiling * 174;
    return (
        <figure className="fan-chart">
            <a href={pdfUrl} target="_blank" rel="noreferrer" aria-label="打开 Yang 论文 PDF 第 4 页">
                <svg viewBox="0 0 392 242" role="img" aria-label="中温和高温各阶段的 FAN 浓度对照">
                    <text x="48" y="15">FAN（mg/L）</text>
                    {[0, 1, 2, 3, 4, 5].map(tick => {
                        const value = ceiling * tick / 5;
                        return <g key={tick}><line x1="48" x2="356" y1={y(value)} y2={y(value)} /><text x="40" y={y(value) + 4} textAnchor="end">{value}</text></g>;
                    })}
                    {series[0].map(point => <text key={point.phase} x={x(point.phase)} y="220" textAnchor="middle">{point.phase}</text>)}
                    <text x="202" y="238" textAnchor="middle">实验阶段</text>
                    {series.map((points, index) => <g key={index} stroke={colors[index]} fill={colors[index]}>
                        <polyline fill="none" strokeWidth="2.5" strokeDasharray={index ? "5 3" : undefined}
                            points={points.map(point => `${x(point.phase)},${y(point.value)}`).join(" ")} />
                        {points.map(point => <circle key={point.phase} cx={x(point.phase)} cy={y(point.value)} r="3">
                            <title>{index ? "高温" : "中温"} · 阶段 {point.phase} · {point.value} mg/L</title>
                        </circle>)}
                    </g>)}
                </svg>
            </a>
            <figcaption><span className="fan-meso">● 中温</span> <span className="fan-thermo">● 高温</span> · 据 Yang 等（2018）表 1 重绘</figcaption>
        </figure>
    );
}

