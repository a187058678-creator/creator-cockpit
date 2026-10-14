export const metadata = {
  title: "Creator Cockpit",
  description: "Creator Cockpit Web"
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body
        style={{
          margin: 0,
          background: "#0b1020",
          color: "#e5e7eb",
          fontFamily:
            'Inter, Arial, "PingFang SC", "Microsoft YaHei", sans-serif',
        }}
      >
        {children}
      </body>
    </html>
  );
}
