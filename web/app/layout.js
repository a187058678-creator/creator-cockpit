export const metadata = {
  title: "Creator Cockpit",
  description: "Creator Cockpit Web"
};

export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
