import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'DeFi Protection Protocol',
  description: 'AI-Powered Liquidation Defense',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  )
}
