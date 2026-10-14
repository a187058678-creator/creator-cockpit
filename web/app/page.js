export default function HomePage() {
  return (
    <main style={{ padding: 24, fontFamily: "Arial, sans-serif" }}>
      <h1>Creator Cockpit Web</h1>
      <p>Web 服务已经部署成功。</p>
      <p>后端地址：{process.env.NEXT_PUBLIC_API_BASE_URL || "未配置"}</p>
    </main>
  );
}
