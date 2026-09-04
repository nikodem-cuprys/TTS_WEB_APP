export function formatBytes(n: number): string {
  let size = n
  for (const unit of ['B', 'KB', 'MB', 'GB']) {
    if (size < 1024) return `${size.toFixed(size < 10 && unit !== 'B' ? 1 : 0)}${unit}`
    size /= 1024
  }
  return `${size.toFixed(1)}TB`
}
